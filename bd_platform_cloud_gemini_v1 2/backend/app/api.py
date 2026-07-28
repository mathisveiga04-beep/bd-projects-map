"""
Endpoints API pour la couche "Appels d'offre ASEAN".
Routes prefixees /ao -> N'ENTRENT PAS en conflit avec le /tenders (CRM) existant.

A brancher dans app/main.py :
from .ao_ingest.api import router as ao_router
app.include_router(ao_router)

Lectures : via PostgREST (cle anon) -> la RLS ne renvoie que verified+kept.
Ingestion : protegee par l'auth admin existante (verify_app_or_jwt + require_admin_token).
"""
from __future__ import annotations
import json
import logging
import os
import urllib.parse
import urllib.request
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Header

logger = logging.getLogger("ao")

router = APIRouter(prefix="/ao", tags=["appels-offre"])

# Reutilise les variables d'environnement DEJA presentes sur le service Render.
# (l'app existante expose SUPABASE_KEY / SUPABASE_SERVICE_ROLE_KEY ; on les accepte
# en plus des noms canoniques, pour ne RIEN avoir a re-saisir cote Render).
SUPABASE_URL = (os.getenv("SUPABASE_URL")
                or "https://xyvsfkalaeatwmcobwrg.supabase.co").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY", "")

# Colonnes pour la carte (charger leger mais riche en relationnel).
# Contrat aligne sur le frontend (tenderFromApi + mkIcon) :
# relevance_score -> "fit" (liste) + "pot" (couleur du pin)
# issuer_name / donor / authority -> "funder"
# building_subsector / sector / discipline -> "type" (forme du pin)
# Champs relationnels ajoutes (migration_004) : donor, ministry, authority,
# project_name, project_ref, discipline, city, country_name + FKs entites.
MAP_COLS = ("id,title,country_iso2,country_name,city,sector,discipline,"
            "building_subsector,stage,procurement_type,"
            "value_amount,value_currency,deadline_at,lat,lng,"
            "relevance_score,issuer_name,source_code,source_url,"
            "donor,ministry,authority,project_name,project_ref,"
            "project_uid,donor_org_id,authority_org_id,language")
FULL_COLS = "*"

# Colonnes entites (lecture publique via RLS sur les tables ao_*).
PROJECT_COLS = ("id,external_id,source_code,name,country_iso2,city,"
                "latitude,longitude,donor_org_id,authority_org_id,"
                "sector,discipline,estimated_budget,currency,status,source_url")
PROJECT_COLS_DATED = PROJECT_COLS + ",created_at,updated_at"
ORG_COLS = "id,name,org_type,country_iso2,acronym,source_url"
COMPANY_COLS = "id,name,company_type,country_iso2,website,source_url"
ROLE_COLS = ("id,role,tender_id,project_uid,company_id,organisation_id,"
             "person_id,source_url")

def _sb_get(path: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers={
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {ANON_KEY}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

@router.get("/tenders")
def list_tenders(
    country: Optional[str] = Query(None, description="ISO2, ex: KH"),
    stage: Optional[str] = None,
    sector: Optional[str] = None,
    discipline: Optional[str] = Query(None, description="ex: hvac, mep, structure"),
    donor: Optional[str] = Query(None, description="ex: World Bank, ADB"),
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    deadline_after: Optional[str] = None,
    include_expired: bool = Query(False, description="Inclure les AO dont la date limite est passee"),
    limit: int = Query(500, le=2000),
    offset: int = 0,
):
    """Liste filtree/paginee, colonnes carte uniquement. RLS = verified+kept only."""
    params = [("select", MAP_COLS), ("limit", str(limit)), ("offset", str(offset)),
              ("order", "deadline_at.asc.nullslast")]
    if country:
        params.append(("country_iso2", f"eq.{country.upper()}"))
    if stage:
        params.append(("stage", f"eq.{stage}"))
    if sector:
        params.append(("sector", f"ilike.*{sector}*"))
    if discipline:
        params.append(("discipline", f"eq.{discipline}"))
    if donor:
        params.append(("donor", f"ilike.*{donor}*"))
    if deadline_after:
        params.append(("deadline_at", f"gte.{deadline_after}"))
    elif not include_expired:
        _today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        params.append(("deadline_at", f"gte.{_today}"))
    if bbox:
        try:
            min_lng, min_lat, max_lng, max_lat = [float(x) for x in bbox.split(",")]
            params += [("lng", f"gte.{min_lng}"), ("lng", f"lte.{max_lng}"),
                       ("lat", f"gte.{min_lat}"), ("lat", f"lte.{max_lat}")]
        except ValueError:
            raise HTTPException(400, "bbox invalide (attendu: minLng,minLat,maxLng,maxLat)")
    qs = urllib.parse.urlencode(params)
    try:
        return _sb_get(f"ao_tenders?{qs}")
    except Exception as e:
        logger.exception("Lecture tenders impossible")
        raise HTTPException(502, "Lecture des appels d'offre temporairement indisponible.")

@router.get("/tenders/{tender_id}")
def get_tender(tender_id: int):
    qs = urllib.parse.urlencode([("select", FULL_COLS), ("id", f"eq.{tender_id}")])
    rows = _sb_get(f"ao_tenders?{qs}")
    if not rows:
        raise HTTPException(404, "Tender introuvable")
    return rows[0]

# --- Entites du graphe relationnel (lecture publique via RLS) -----------------
@router.get("/projects")
def list_projects(
    country: Optional[str] = Query(None, description="ISO2, ex: KH"),
    sector: Optional[str] = None,
    discipline: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filtre statut exact, ex: open"),
    include_finished: bool = Query(False, description="Inclure les projets termines (closed/awarded)"),
    limit: int = Query(500, le=2000),
    offset: int = 0,
):
    """Projets (un projet agrege plusieurs AO). Sert la future vue 'par projet'."""
    filters = []
    if country:
        filters.append(("country_iso2", f"eq.{country.upper()}"))
    if sector:
        filters.append(("sector", f"ilike.*{sector}*"))
    if discipline:
        filters.append(("discipline", f"eq.{discipline}"))
    if status:
        filters.append(("status", f"eq.{status}"))
    elif not include_finished:
        filters.append(("status", "not.in.(closed,awarded)"))
    tail = [("limit", str(limit)), ("offset", str(offset)), ("order", "name.asc")]
    try:
        # On expose les colonnes date si elles existent en base ; repli transparent sinon.
        dated = [("select", PROJECT_COLS_DATED)] + filters + tail
        return _sb_get(f"ao_projects?{urllib.parse.urlencode(dated)}")
    except Exception:
        try:
            base = [("select", PROJECT_COLS)] + filters + tail
            return _sb_get(f"ao_projects?{urllib.parse.urlencode(base)}")
        except Exception:
            logger.exception("Lecture projects impossible")
            raise HTTPException(502, "Lecture des projets temporairement indisponible.")

@router.get("/organisations")
def list_organisations(
    country: Optional[str] = Query(None, description="ISO2 ; absent = bailleurs multilateraux"),
    org_type: Optional[str] = Query(None, description="ministry|authority|agency|donor|mdb|other"),
    limit: int = Query(500, le=2000),
    offset: int = 0,
):
    """Organisations : ministeres, autorites, agences, bailleurs (noeuds du reseau)."""
    params = [("select", ORG_COLS), ("limit", str(limit)), ("offset", str(offset)),
              ("order", "name.asc")]
    if country:
        params.append(("country_iso2", f"eq.{country.upper()}"))
    if org_type:
        params.append(("org_type", f"eq.{org_type}"))
    qs = urllib.parse.urlencode(params)
    try:
        return _sb_get(f"ao_organisations?{qs}")
    except Exception as e:
        logger.exception("Lecture organisations impossible")
        raise HTTPException(502, "Lecture des organisations temporairement indisponible.")

@router.get("/companies")
def list_companies(
    country: Optional[str] = Query(None, description="ISO2"),
    company_type: Optional[str] = Query(None, description="consultant|contractor|..."),
    limit: int = Query(500, le=2000),
    offset: int = 0,
):
    """Entreprises (consultants, contractors, ...) : noeuds 'prive' du reseau."""
    params = [("select", COMPANY_COLS), ("limit", str(limit)), ("offset", str(offset)),
              ("order", "name.asc")]
    if country:
        params.append(("country_iso2", f"eq.{country.upper()}"))
    if company_type:
        params.append(("company_type", f"eq.{company_type}"))
    qs = urllib.parse.urlencode(params)
    try:
        return _sb_get(f"ao_companies?{qs}")
    except Exception as e:
        logger.exception("Lecture companies impossible")
        raise HTTPException(502, "Lecture des entreprises temporairement indisponible.")

@router.get("/tenders/{tender_id}/parties")
def tender_parties(tender_id: int):
    """Roles des parties (qui fait quoi) sur un AO -> alimente le graphe d'acteurs."""
    qs = urllib.parse.urlencode([("select", ROLE_COLS), ("tender_id", f"eq.{tender_id}")])
    try:
        return _sb_get(f"ao_party_roles?{qs}")
    except Exception as e:
        logger.exception("Lecture party_roles impossible")
        raise HTTPException(502, "Lecture des parties temporairement indisponible.")

@router.get("/sources/health")
def sources_health():
    """Page sante : dernier run par source (observabilite du pipeline)."""
    qs = urllib.parse.urlencode([("select", "source_code,status,started_at,finished_at,rows_fetched,rows_upserted,rows_rejected,error_message"),
                                 ("order", "started_at.desc"), ("limit", "50")])
    try:
        return _sb_get(f"ao_ingest_runs?{qs}")
    except Exception as e:
        logger.exception("Lecture ingest_runs impossible")
        raise HTTPException(502, "Lecture de l'etat des sources temporairement indisponible.")

# --- Declenchement de l'ingestion (protege par l'auth admin existante) --------
def _require_admin(authorization: str | None = Header(default=None),
                   x_app_token: str | None = Header(default=None)) -> dict:
    """Reutilise l'auth de main.py (token app OU JWT Supabase role admin).
    Import tardif -> evite tout import circulaire au demarrage."""
    from .main import verify_app_or_jwt, require_admin_token  # type: ignore
    token = verify_app_or_jwt(authorization=authorization, x_app_token=x_app_token)
    return require_admin_token(token)

@router.post("/ingest/run")
def ingest_run(source: str = Query("WB"), _admin: dict = Depends(_require_admin)):
    """Lance une collecte pour une source. A appeler par le cron (GitHub Actions)."""
    from .run import run_source  # import tardif (charge les connecteurs)
    return run_source(source)

@router.post("/ingest/run-all")
def ingest_run_all(_admin: dict = Depends(_require_admin)):
    """Lance toutes les sources enregistrees (un echec n'arrete pas les suivantes)."""
    from .run import run_all
    return run_all()

@router.get("/connectors")
def list_connectors():
    """Liste les sources branchees (debug/observabilite ; non protege)."""
    from .run import CONNECTORS
    return {"connectors": sorted(CONNECTORS.keys())}


@router.get("/version")
def deployed_version():
    """Expose le commit Git deploye (RENDER_GIT_COMMIT) pour detecter un deploiement obsolete (debug/observabilite ; non protege)."""
    return {
        "commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "unknown",
        "branch": os.getenv("RENDER_GIT_BRANCH") or "unknown",
    }
