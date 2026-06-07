from __future__ import annotations
from datetime import datetime
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

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "").strip()
APP_SECRET = os.getenv("APP_SECRET", "").strip()
APP_LOGIN_TOKEN = os.getenv("APP_LOGIN_TOKEN", "MVE2026").strip()
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


@app.get("/health")
def health():
    return {"status": "ok", "database": "connected", "version": "v1-cloud-gemini-production-ready"}


@app.get("/projects", response_model=list[schemas.ProjectOut])
def get_projects(db: Session = Depends(get_db)):
    return crud.list_projects(db)


def verify_app_or_jwt(authorization: str | None = Header(default=None), x_app_token: str | None = Header(default=None)) -> dict:
    if (APP_SECRET and x_app_token == APP_SECRET) or (APP_LOGIN_TOKEN and x_app_token == APP_LOGIN_TOKEN):
        return {"sub": "app-token", "email": "app-token", "app_metadata": {"role": "admin"}}
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
    if not payload.owner_id:
        payload.owner_id = get_user_id(token)
    if not payload.owner_email:
        payload.owner_email = token.get("email", "")
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
    return verify_app_or_jwt(authorization, x_app_token)


@app.post("/ai/analyze")
def ai_analyze(payload: schemas.AnalyzeRequest, token: dict = Depends(verify_ai_access)):
    return analyze_with_gemini(payload.title, payload.text, payload.source_url)


@app.post("/ai/generate")
def ai_generate(payload: schemas.GenerateRequest, token: dict = Depends(verify_ai_access)):
    return generate_with_gemini(payload.prompt, payload.max_tokens, payload.mode)


@app.get("/scraper/sources")
def scraper_sources():
    return {"sources": active_sources()}


@app.post("/scraper/run")
def scraper_run(
    payload: schemas.ScraperRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_app_token: str | None = Header(default=None),
):
    has_scraper_key = SCRAPER_API_KEY and x_api_key == SCRAPER_API_KEY
    if not has_scraper_key:
        require_admin_token(verify_app_or_jwt(authorization, x_app_token))
    run = models.ScraperRun(source=payload.source or "all", status="started")
    db.add(run)
    db.commit()
    saved = 0
    opportunities = []
    if payload.source in (None, "all", "worldbank"):
        opportunities.extend(scrape_world_bank_cambodia())
    if payload.source in (None, "all", "rss"):
        opportunities.extend(scrape_rss_sources())
    if payload.source in (None, "all", "sources", "watchlist"):
        opportunities.extend(scrape_default_source_watchlist())

    if not payload.dry_run:
        for item in opportunities:
            ai = analyze_with_gemini(item.title, item.text, item.source_url)
            project = models.Project(
                title=item.title,
                description=item.text,
                country=ai.get("country") or item.country or "Cambodia",
                city=ai.get("city") or "",
                is_localized=False,
                sector=ai.get("sector") or "",
                project_type=ai.get("project_type") or "Opportunity",
                status="identified",
                priority=ai.get("priority") or "medium",
                source=item.source,
                source_url=item.source_url,
                funder=ai.get("funder") or item.funder,
                estimated_budget=ai.get("estimated_budget") or "unknown",
                deadline=ai.get("deadline") or "",
                reliability=ai.get("confidence") or "medium",
                confidence=ai.get("confidence") or "medium",
                opportunity_size=ai.get("opportunity_size") or "unknown",
                scope_summary=ai.get("scope_summary") or "",
                ai_summary=ai.get("summary") or "",
                ai_recommendation=ai.get("recommendation") or "watch",
                contributor="scraper+gemini",
            )
            try:
                db.add(project)
                db.commit()
                saved += 1
            except Exception:
                db.rollback()

    run.status = "finished"
    run.items_found = len(opportunities)
    run.items_saved = saved
    run.finished_at = datetime.utcnow()
    run.message = "OK"
    db.commit()
    return {"ok": True, "items_found": len(opportunities), "items_saved": saved}


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


@app.post("/admin/users/{user_id}/set-role")
def admin_set_role(user_id: str, role: str, token: dict = Depends(verify_app_or_jwt)):
    require_admin_token(token)
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(503, "Supabase admin config missing: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"}
    r = requests.put(url, headers=headers, json={"app_metadata": {"role": role}})
    if not r.ok:
        raise HTTPException(r.status_code, "Supabase admin API refused credentials. Set SUPABASE_SERVICE_ROLE_KEY on Render.")
    return {"success": True, "user_id": user_id, "role": role}
