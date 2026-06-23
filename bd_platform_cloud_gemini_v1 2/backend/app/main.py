from __future__ import annotations
import secrets as _secrets
from datetime import datetime, date
import os
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
from .scrapers.rss import scrape_rss_sources
from .scrapers.source_watchlist import scrape_default_source_watchlist

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
def get_projects(db: Session = Depends(get_db)):
    return crud.list_projects(db)


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
    saved = 0
    skipped = 0
    failed = 0
    opportunities = []
    if payload.source in (None, "all", "worldbank"):
        opportunities.extend(scrape_world_bank_cambodia())
    if payload.source in (None, "all", "rss"):
        opportunities.extend(scrape_rss_sources())
    if payload.source in (None, "all", "sources", "watchlist"):
        opportunities.extend(scrape_default_source_watchlist())

    # Borne le travail par run pour rester sous le timeout de la passerelle Render.
    if getattr(payload, "limit", 0) and payload.limit > 0:
        opportunities = opportunities[: payload.limit]
    if not payload.dry_run:
        errors = []
        for item in opportunities:
            try:
                ai = analyze_with_gemini(item.title, item.text, item.source_url)
                # Filtre de pertinence: ignorer les appels d'offre dont la date limite est depassee
                # (date du jour dynamique). Les prospects de renovation sans date sont conserves.
                if _is_past_deadline(str(ai.get("deadline") or "")):
                    skipped += 1
                    continue
                project = schemas.ProjectCreate(
                    title=item.title,
                    description=item.text,
                    country=str(ai.get("country") or item.country or "Cambodia"),
                    city=str(ai.get("city") or ""),
                    is_localized=False,
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
        "items_found": len(opportunities),
        "items_saved": saved,
        "items_skipped": skipped,
        "items_failed": failed,
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
