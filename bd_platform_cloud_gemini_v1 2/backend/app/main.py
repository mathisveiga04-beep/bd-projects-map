from __future__ import annotations
import secrets as _secrets
from datetime import datetime, date
import os
import logging
import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from . import crud, models, schemas
from .ai import analyze_with_gemini, generate_with_gemini
from .auth import get_user_id, get_user_role, verify_supabase_jwt
from .sources import active_sources
from .scrapers.worldbank import scrape_world_bank_cambodia
from .scrapers.adb import scrape_adb_cambodia
from .scrapers.iati import scrape_iati_sea, iati_fallback_ai
from .scrapers.geo import geocode
from .scrapers.rss import scrape_rss_sources
from .scrapers.source_watchlist import scrape_default_source_watchlist
from .official_status import official_status_to_fr

Base.metadata.create_all(bind=engine)

# Migration legere et idempotente : synchronise les colonnes manquantes
# sur les bases deja existantes (create_all n'ajoute jamais de colonne).
try:
    from sqlalchemy import inspect as _sa_inspect
    _insp = _sa_inspect(engine)
    _models_to_sync = [m for m in (getattr(models, "Project", None), getattr(models, "Tender", None)) if m is not None]
    for _model in _models_to_sync:
        _table = _model.__tablename__
        _existing = {col["name"] for col in _insp.get_columns(_table)}
        with engine.begin() as _mig_conn:
            for _col in _model.__table__.columns:
                if _col.name not in _existing:
                    _type_sql = _col.type.compile(dialect=engine.dialect)
                    _mig_conn.exec_driver_sql(
                        f'ALTER TABLE "{_table}" ADD COLUMN IF NOT EXISTS "{_col.name}" {_type_sql}'
                    )
except Exception as _mig_err:  # pragma: no cover
    print(f"[migration] column sync: {_mig_err}")

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "").strip()
APP_SECRET = os.getenv("APP_SECRET", "").strip()
# APP_LOGIN_TOKEN supprime: plus de token partage admin (securite)

# --- In-memory rate limiter for AI routes (no extra deps, fail-safe) ---
import time as _time
AI_RATE_LIMIT_PER_MIN = int(os.getenv("AI_RATE_LIMIT_PER_MIN", "20"))
_AI_RATE_WINDOW = 60.0
_ai_rate_hits: dict[str, list[float]] = {}

def _enforce_ai_rate_limit(key: str) -> None:
    if AI_RATE_LIMIT_PER_MIN <= 0:
        return
    now = _time.time()
    cutoff = now - _AI_RATE_WINDOW
    hits = [t for t in _ai_rate_hits.get(key, []) if t >= cutoff]
    if len(hits) >= AI_RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Trop de requetes IA. Patientez une minute.")
    hits.append(now)
    _ai_rate_hits[key] = hits
ALLOWED_ORIGINS = [
    "https://bd-projects-map.vercel.app",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
]

app = FastAPI(title="BD Intelligence Platform API", version="1.0-cloud-gemini-production-ready")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "database": "connected", "version": "v1-cloud-gemini-production-ready"}


@app.get("/projects", response_model=list[schemas.ProjectOut])
def get_projects(include_archived: bool = False, db: Session = Depends(get_db)):
    # Par defaut on masque les projets archives par le re-audit (perimes / hors corps d etat /
    # cycle de vie lance ou termine). include_archived=true pour les recuperer si besoin.
    items = crud.list_projects(db)
    if not include_archived:
        items = [p for p in items if getattr(p, "status", "") != "archived"]
    return items


@app.get("/projects_debug")
def projects_debug(db: Session = Depends(get_db)):
    """Diagnostic temporaire: identifie la ligne/erreur qui fait planter /projects."""
    import traceback
    out = {"stage": "start"}
    try:
        out["stage"] = "query"
        items = crud.list_projects(db)
        out["count"] = len(items)
        out["stage"] = "validate"
        errors = []
        for it in items:
            try:
                schemas.ProjectOut.model_validate(it)
            except Exception as e:
                errors.append({"id": getattr(it, "id", None), "error": str(e)[:600]})
                if len(errors) >= 3:
                    break
        out["validation_errors"] = errors
        out["stage"] = "done"
        return out
    except Exception as e:
        out["error"] = str(e)[:1000]
        out["traceback"] = traceback.format_exc()[:2500]
        return out


def verify_app_or_jwt(authorization: str | None = Header(default=None), x_app_token: str | None = Header(default=None)) -> dict:
    # SECURITE: bypass par token partage supprime - JWT Supabase obligatoire.
    return verify_supabase_jwt(authorization)


def require_admin_token(token: dict) -> dict:
    if get_user_role(token) != "admin":
        raise HTTPException(403, "Admin access required")
    return token


def ensure_project_access(project: models.Project | None, token: dict) -> None:
    if not project:
        raise HTTPException(404, "Project not found")
    if get_user_role(token) == "admin":
        return
    if project.owner_id and project.owner_id == get_user_id(token):
        return
    raise HTTPException(403, "Project owner or admin access required")


@app.post("/projects", response_model=schemas.ProjectOut)
def post_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db), token: dict = Depends(verify_app_or_jwt)):
    # Si la creation correspond a un projet existant, c est une modification deguisee :
    # on exige les memes droits que sur PATCH (proprietaire ou admin).
    existing = crud.find_project_match(db, payload)
    if existing:
        ensure_project_access(existing, token)
    # Propriete definie cote serveur (anti-usurpation) : on ignore toute valeur client.
    payload.owner_id = get_user_id(token)
    payload.owner_email = token.get("email", "") or payload.owner_email
    payload.is_localized = bool(payload.latitude is not None and payload.longitude is not None)
    return crud.create_project(db, payload)


@app.patch("/projects/{project_id}", response_model=schemas.ProjectOut)
def patch_project(project_id: int, payload: schemas.ProjectUpdate, db: Session = Depends(get_db), token: dict = Depends(verify_app_or_jwt)):
    ensure_project_access(db.get(models.Project, project_id), token)
    obj = crud.update_project(db, project_id, payload)
    if not obj:
        raise HTTPException(404, "Project not found")
    return obj


@app.delete("/projects/{project_id}")
def remove_project(project_id: int, db: Session = Depends(get_db), token: dict = Depends(verify_app_or_jwt)):
    require_admin_token(token)
    if not crud.delete_project(db, project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@app.get("/tenders", response_model=list[schemas.TenderOut])
def get_tenders(db: Session = Depends(get_db)):
    return crud.list_tenders(db)


@app.post("/tenders", response_model=schemas.TenderOut)
def post_tender(payload: schemas.TenderCreate, db: Session = Depends(get_db), token: dict = Depends(verify_app_or_jwt)):
    return crud.create_tender(db, payload)


def verify_ai_access(authorization: str | None = Header(default=None), x_app_token: str | None = Header(default=None)) -> dict:
    token = verify_app_or_jwt(authorization, x_app_token)
    _enforce_ai_rate_limit(str(token.get("sub") or "anon"))
    return token


@app.post("/ai/analyze")
def ai_analyze(payload: schemas.AnalyzeRequest, token: dict = Depends(verify_ai_access)):
    return analyze_with_gemini(payload.title, payload.text, payload.source_url)


@app.post("/ai/generate")
def ai_generate(payload: schemas.GenerateRequest, token: dict = Depends(verify_ai_access)):
    return generate_with_gemini(payload.prompt, payload.max_tokens, payload.mode)


@app.get("/scraper/sources")
def scraper_sources():
    return {"sources": active_sources()}


def _is_past_deadline(deadline_str: str) -> bool:
    """True si la date limite (deadline) est strictement anterieure a aujourd'hui.
    Date du jour dynamique via date.today(). Chaine vide / non datable -> False (conservee)."""
    import re as _re
    s = (deadline_str or "").strip()
    if not s:
        return False
    today = date.today()
    m = _re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) < today
        except ValueError:
            return False
    m = _re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) < today
        except ValueError:
            return False
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
              "janv":1,"fevr":2,"mars":3,"avr":4,"mai":5,"juin":6,"juil":7,"aout":8,"sept":9,"octo":10,"nove":11,"dece":12}
    low = s.lower()
    ym = _re.search(r"(20\d{2})", low)
    if ym:
        year = int(ym.group(1))
        mon = None
        for k, v in months.items():
            if k in low:
                mon = v
                break
        if mon is None:
            return year < today.year
        try:
            from calendar import monthrange
            last_day = monthrange(year, mon)[1]
            return date(year, mon, last_day) < today
        except ValueError:
            return year < today.year
    return False


def _status_is_pending(value) -> bool:
    """True uniquement si le statut cycle de vie correspond a en attente / preparation preliminaire."""
    import unicodedata
    raw = ("" if value is None else str(value)).strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    if not raw:
        return True
    launched = ("demarr", "en cours", "termin", "annul", "started", "ongoing",
                "completed", "cancelled", "awarded", "in progress", "underway")
    if any(k in raw for k in launched):
        return False
    return ("attente" in raw or "pending" in raw or "prepar" in raw
            or "preliminaire" in raw or "planned" in raw or "identif" in raw)


_official_status_to_fr = official_status_to_fr


_INSCOPE_SECTOR_KEYWORDS = (
    "water", "eau", "wastewater", "assainissement", "drainage", "flood", "hydraulic", "hydraulique",
    "sanitation", "sewer", "irrigation",
    "road", "route", "bridge", "pont", "transport", "mobilit", "rail", "port", "airport", "infrastructure",
    "energy", "energie", "power", "grid", "reseau", "renewable", "renouvelable", "solar", "wind",
    "electric", "climate", "resilience", "resilienc",
    "building", "batiment", "construction", "architecture", "environment", "environnement",
    "urban", "urbain", "pmo", "pmc", "supervision", "engineering", "ingenierie", "consultanc", "conseil",
    "drain", "dam", "barrage", "treatment", "traitement",
)


def _sector_in_scope(value) -> bool:
    """True si le secteur est dans l un des 4 corps d etat couverts (sinon hors perimetre)."""
    import unicodedata
    raw = ("" if value is None else str(value)).strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    if not raw:
        return True
    return any(k in raw for k in _INSCOPE_SECTOR_KEYWORDS)


def _is_eligible_opportunity(ai: dict) -> bool:
    """Consigne stricte: ne garder que les opportunites en attente/preparation, a valeur
    ajoutee aujourd hui, dans les corps d etat couverts. Sinon on n enregistre pas."""
    rec = str((ai or {}).get("recommendation") or "").strip().lower()
    if rec in ("discard", "skip", "ignore", "reject"):
        return False
    if not _status_is_pending((ai or {}).get("project_status")):
        return False
    if not _sector_in_scope((ai or {}).get("sector")):
        return False
    return True


_STALE_YEAR_GAP = 2


def _text_has_stale_year(*values) -> bool:
    """True si un titre/description contient une annee clairement passee (<= annee courante -
    _STALE_YEAR_GAP), signal d un vieil appel d offre meme sans deadline datee (ex: AO 1988)."""
    import re as _re
    cutoff = date.today().year - _STALE_YEAR_GAP
    for value in values:
        raw = "" if value is None else str(value)
        for m in _re.findall(r"\b(19\d{2}|20\d{2})\b", raw):
            try:
                y = int(m)
            except ValueError:
                continue
            if 1980 <= y <= cutoff:
                return True
    return False


def _project_is_stale(project) -> bool:
    """Re-audit: True si un projet existant n est plus pertinent aujourd hui
    (deadline depassee, cycle de vie lance/termine/annule, ou hors corps d etat)."""
    try:
        if _is_past_deadline(str(getattr(project, "deadline", "") or "")):
            return True
        if not _status_is_pending(getattr(project, "project_status", "")):
            return True
        if not _sector_in_scope(getattr(project, "sector", "")):
            return True
        if _text_has_stale_year(getattr(project, "title", ""), getattr(project, "description", ""),
                                getattr(project, "ai_summary", ""), getattr(project, "scope_summary", "")):
            return True
    except Exception:
        return False
    return False


@app.post("/scraper/run")
def scraper_run(
    payload: schemas.ScraperRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_app_token: str | None = Header(default=None),
):
    has_scraper_key = bool(SCRAPER_API_KEY) and _secrets.compare_digest(x_api_key or "", SCRAPER_API_KEY)
    if not has_scraper_key:
        require_admin_token(verify_app_or_jwt(authorization, x_app_token))
    run = models.ScraperRun(source=payload.source or "all", status="started")
    db.add(run)
    db.commit()
    # Re-audit quotidien (verification integree au scraper): on archive les projets
    # existants devenus non pertinents (deadline depassee, cycle de vie lance/termine/
    # annule, ou hors corps d etat) au lieu de les supprimer (reversible).
    audited = 0
    archived = 0
    try:
        for _p in crud.list_projects(db):
            if getattr(_p, "status", "") == "archived":
                continue
            if _project_is_stale(_p):
                _p.status = "archived"
                _p.watch_status = "archived"
                archived += 1
            audited += 1
        if archived:
            db.commit()
    except Exception:
        db.rollback()
    saved = 0
    skipped = 0
    failed = 0
    expired = 0
    ai_errors = 0
    ai_error_sample = []
    opportunities = []
    _buckets = []
    if payload.source in (None, "all", "worldbank"):
        _buckets.append(scrape_world_bank_cambodia())
    if payload.source in (None, "all", "adb"):
        _buckets.append(scrape_adb_cambodia())
    if payload.source in (None, "all", "iati"):
        _buckets.append(scrape_iati_sea())
    if payload.source in (None, "all", "rss"):
        _buckets.append(scrape_rss_sources())
    if payload.source in (None, "all", "sources", "watchlist"):
        _wl = scrape_default_source_watchlist()
        # Rotation par run : chaque execution decale la fenetre de la watchlist
        # afin de couvrir TOUS les emetteurs au fil des runs (le plafond borne le travail par run).
        if _wl:
            _off = (getattr(run, "id", 0) or 0) % len(_wl)
            _wl = _wl[_off:] + _wl[:_off]
        _buckets.append(_wl)

    # Entrelacement round-robin : aucune source ne monopolise le plafond ;
    # toutes les sources (Banque mondiale, RSS, watchlist) sont representees.
    _idx = 0
    while True:
        _added = False
        for _b in _buckets:
            if _idx < len(_b):
                opportunities.append(_b[_idx])
                _added = True
        if not _added:
            break
        _idx += 1

    # Borne le travail par run pour rester sous le timeout de la passerelle Render.
    # Budget d'appels IA par run (au lieu de tronquer la liste): on scanne large et on ne
    # depense du quota Gemini que sur les items reellement nouveaux.
    _ai_budget = payload.limit if (getattr(payload, "limit", 0) and payload.limit > 0) else 20
    _quota_exhausted = False  # verrou: bascule sur le repli des le 1er 429, sans re-solliciter Gemini
    opportunities = opportunities[:400]  # borne de securite sur le nombre d'items scannes / run
    if not payload.dry_run:
        errors = []
        for item in opportunities:
            try:
                if crud.project_exists(db, item.title, item.source_url):
                    try:
                        _fr_exist = _official_status_to_fr(getattr(item, "official_status", ""))
                        if _fr_exist:
                            crud.refresh_status_by_key(db, item.title, item.source_url, _fr_exist)
                    except Exception:
                        pass
                    skipped += 1
                    continue
                if _quota_exhausted:
                    ai = {"ai_error": "RESOURCE_EXHAUSTED (verrou quota: appel Gemini evite)"}
                else:
                    if _ai_budget <= 0:
                        break
                    _ai_budget -= 1
                    ai = analyze_with_gemini(item.title, item.text, item.source_url)
                if ai.get("ai_error"):
                    ai_errors += 1
                    if len(ai_error_sample) < 3:
                        ai_error_sample.append(str(ai.get("ai_error"))[:300])
                    _err = str(ai.get("ai_error"))
                    if "RESOURCE_EXHAUSTED" in _err or "429" in _err or "quota" in _err.lower():
                        _quota_exhausted = True
                        # Quota Gemini epuise: repli deterministe (sans IA) pour les items IATI,
                        # afin de continuer a enregistrer les projets meme sans enrichissement IA.
                        _fb = iati_fallback_ai(
                            getattr(item, "source", ""),
                            getattr(item, "official_status", ""),
                            item.title, item.text,
                            getattr(item, "country", ""),
                        )
                        if _fb is None:
                            skipped += 1
                            continue
                        ai = _fb
                _raw_official = getattr(item, "official_status", "")
                _official = _official_status_to_fr(_raw_official)
                if _official:
                    ai["project_status"] = _official
                elif str(_raw_official or "").strip():
                    logging.warning(
                        "Statut officiel non reconnu (repli IA) : %r [source=%s]",
                        _raw_official, getattr(item, "source", ""),
                    )
                # Filtre de pertinence: ignorer les appels d'offre dont la date limite est depassee
                # (date du jour dynamique). Les prospects de renovation sans date sont conserves.
                if _is_past_deadline(str(ai.get("deadline") or "")):
                    expired += 1
                    continue
                if not _is_eligible_opportunity(ai):
                    skipped += 1
                    continue
                _geo = geocode(str(ai.get("country") or item.country or "Cambodia"), str(ai.get("city") or ""))
                project = schemas.ProjectCreate(
                    title=item.title,
                    description=item.text,
                    country=str(ai.get("country") or item.country or "Cambodia"),
                    city=str(ai.get("city") or ""),
                    latitude=_geo[0],
                    longitude=_geo[1],
                    is_localized=bool(_geo[0] is not None and _geo[1] is not None),
                    sector=str(ai.get("sector") or ""),
                    project_type=str(ai.get("project_type") or "Opportunity"),
                    status="identified",
                    project_status=str(ai.get("project_status") or ""),
                    priority=str(ai.get("priority") or "medium").lower(),
                    source=item.source,
                    source_url=item.source_url,
                    funder=str(ai.get("funder") or item.funder or ""),
                    estimated_budget=str(ai.get("estimated_budget") or "unknown"),
                    deadline=str(ai.get("deadline") or ""),
                    reliability=str(ai.get("confidence") or "medium"),
                    confidence=str(ai.get("confidence") or "medium"),
                    opportunity_size=str(ai.get("opportunity_size") or "unknown"),
                    scope_summary=str(ai.get("scope_summary") or ""),
                    ai_summary=str(ai.get("summary") or ""),
                    ai_recommendation=str(ai.get("recommendation") or "watch"),
                    contributor="scraper+gemini",
                )
                _obj, created = crud.create_or_update_project(db, project)
                if created:
                    saved += 1
                else:
                    skipped += 1
            except Exception as exc:
                db.rollback()
                failed += 1
                if len(errors) < 3:
                    errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")

    run.status = "finished"
    run.items_found = len(opportunities)
    run.items_saved = saved
    run.finished_at = datetime.utcnow()
    run.message = f"OK - skipped {skipped}, failed {failed}"
    db.commit()
    return {
        "ok": True,
        "audited": audited,
        "archived": archived,
        "items_found": len(opportunities),
        "items_saved": saved,
        "items_skipped": skipped,
        "items_failed": failed,
        "items_expired": expired,
        "ai_errors": ai_errors,
        "ai_error_sample": ai_error_sample,
        "errors": errors,
    }


# ── Admin config ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or SUPABASE_KEY


@app.get("/admin/users")
def admin_list_users(token: dict = Depends(verify_app_or_jwt)):
    require_admin_token(token)
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(503, "Supabase admin config missing: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
    r = requests.get(url, headers=headers, params={"page": 1, "per_page": 100})
    if not r.ok:
        raise HTTPException(r.status_code, "Supabase admin API refused credentials. Set SUPABASE_SERVICE_ROLE_KEY on Render.")
    return r.json()


ALLOWED_ROLES = {"user", "admin"}


@app.post("/admin/users/{user_id}/set-role")
def admin_set_role(user_id: str, role: str, token: dict = Depends(verify_app_or_jwt)):
    require_admin_token(token)
    if role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Role invalide. Valeurs autorisees: {sorted(ALLOWED_ROLES)}")
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(503, "Supabase admin config missing: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}
    r = requests.put(url, headers=headers, json={"app_metadata": {"role": role}})
    if not r.ok:
        raise HTTPException(r.status_code, "Supabase admin API refused credentials. Set SUPABASE_SERVICE_ROLE_KEY on Render.")
    return {"success": True, "user_id": user_id, "role": role}
from .api import router as ao_router
app.include_router(ao_router)
