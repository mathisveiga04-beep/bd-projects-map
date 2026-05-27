from datetime import datetime
import os
import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from . import crud, models, schemas
from .ai import analyze_with_gemini
from .auth import verify_supabase_jwt
from .scrapers.worldbank import scrape_world_bank_cambodia
from .scrapers.rss import scrape_rss_sources

Base.metadata.create_all(bind=engine)

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "").strip()
APP_SECRET = os.getenv("APP_SECRET", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

app = FastAPI(title="BD Intelligence Platform API", version="1.0-cloud-gemini-production-ready")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Supabase REST helpers ---------------------------------------------------

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

def supabase_url_exists(source_url: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY or not source_url:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/projects",
            headers=_sb_headers(),
            params={"source_url": f"eq.{source_url}", "select": "id", "limit": "1"},
            timeout=8,
        )
        return r.status_code == 200 and len(r.json()) > 0
    except Exception:
        return False

def insert_to_supabase(data: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        headers = _sb_headers()
        headers["Prefer"] = "return=minimal"
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/projects",
            json=data,
            headers=headers,
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False

# -- Routes -----------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "database": "connected", "version": "v1-cloud-gemini-production-ready"}

@app.get("/projects", response_model=list[schemas.ProjectOut])
def get_projects(db: Session = Depends(get_db)):
    return crud.list_projects(db)

@app.post("/projects", response_model=schemas.ProjectOut)
def post_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db), token: dict = Depends(verify_supabase_jwt)):
    payload.is_localized = bool(payload.latitude is not None and payload.longitude is not None)
    return crud.create_project(db, payload)

@app.patch("/projects/{project_id}", response_model=schemas.ProjectOut)
def patch_project(project_id: int, payload: schemas.ProjectUpdate, db: Session = Depends(get_db), token: dict = Depends(verify_supabase_jwt)):
    obj = crud.update_project(db, project_id, payload)
    if not obj:
        raise HTTPException(404, "Project not found")
    return obj

@app.delete("/projects/{project_id}")
def remove_project(project_id: int, db: Session = Depends(get_db), token: dict = Depends(verify_supabase_jwt)):
    if not crud.delete_project(db, project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}

@app.get("/tenders", response_model=list[schemas.TenderOut])
def get_tenders(db: Session = Depends(get_db)):
    return crud.list_tenders(db)

@app.post("/tenders", response_model=schemas.TenderOut)
def post_tender(payload: schemas.TenderCreate, db: Session = Depends(get_db), token: dict = Depends(verify_supabase_jwt)):
    return crud.create_tender(db, payload)

def verify_ai_access(authorization: str | None = Header(default=None), x_app_token: str | None = Header(default=None)) -> dict:
    if APP_SECRET and x_app_token == APP_SECRET:
        return {"sub": "app-token", "app_metadata": {"role": "admin"}}
    return verify_supabase_jwt(authorization)

@app.post("/ai/analyze")
def ai_analyze(payload: schemas.AnalyzeRequest, token: dict = Depends(verify_ai_access)):
    return analyze_with_gemini(payload.title, payload.text, payload.source_url)

@app.post("/scraper/run")
def scraper_run(payload: schemas.ScraperRequest, db: Session = Depends(get_db), x_api_key: str | None = Header(default=None)):
    if SCRAPER_API_KEY and x_api_key != SCRAPER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing scraper API key")

    run = models.ScraperRun(source=payload.source or "all", status="started")
    db.add(run)
    db.commit()

    saved = 0
    skipped = 0
    opportunities = []

    if payload.source in (None, "all", "worldbank"):
        opportunities.extend(scrape_world_bank_cambodia())
    if payload.source in (None, "all", "rss"):
        opportunities.extend(scrape_rss_sources())

    if not payload.dry_run:
        for item in opportunities:
            if item.source_url and supabase_url_exists(item.source_url):
                skipped += 1
                continue

            ai = analyze_with_gemini(item.title, item.text, item.source_url)

            project_data = {
                "title": item.title,
                "description": item.text,
                "country": ai.get("country") or item.country or "Cambodia",
                "city": ai.get("city") or "",
                "is_localized": False,
                "sector": ai.get("sector") or "",
                "project_type": ai.get("project_type") or "Opportunity",
                "status": "identified",
                "priority": ai.get("priority") or "medium",
                "source": item.source,
                "source_url": item.source_url,
                "funder": ai.get("funder") or item.funder,
                "estimated_budget": ai.get("estimated_budget") or "unknown",
                "deadline": ai.get("deadline") or "",
                "reliability": ai.get("confidence") or "medium",
                "confidence": ai.get("confidence") or "medium",
                "opportunity_size": ai.get("opportunity_size") or "unknown",
                "scope_summary": ai.get("scope_summary") or "",
                "ai_summary": ai.get("summary") or "",
                "ai_recommendation": ai.get("recommendation") or "watch",
                "contributor": "scraper+gemini",
            }

            if insert_to_supabase(project_data):
                saved += 1
            else:
                try:
                    project = models.Project(**project_data)
                    db.add(project)
                    db.commit()
                    saved += 1
                except Exception:
                    db.rollback()

    run.status = "finished"
    run.items_found = len(opportunities)
    run.items_saved = saved
    run.finished_at = datetime.utcnow()
    run.message = "OK - " + str(skipped) + " duplicates skipped"
    db.commit()

    return {
        "ok": True,
        "items_found": len(opportunities),
        "items_saved": saved,
        "items_skipped": skipped,
    }

# -- Admin ------------------------------------------------------------------

@app.get("/admin/users")
def admin_list_users(token: dict = Depends(verify_supabase_jwt)):
    from .auth import get_user_role
    if get_user_role(token) != "admin":
        raise HTTPException(403, "Admin access required")
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(url, headers=headers, params={"page": 1, "per_page": 100})
    r.raise_for_status()
    return r.json()

@app.post("/admin/users/{user_id}/set-role")
def admin_set_role(user_id: str, role: str, token: dict = Depends(verify_supabase_jwt)):
    from .auth import get_user_role
    if get_user_role(token) != "admin":
        raise HTTPException(403, "Admin access required")
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    r = requests.put(url, headers=headers, json={"app_metadata": {"role": role}})
    r.raise_for_status()
    return {"success": True, "user_id": user_id, "role": role}
