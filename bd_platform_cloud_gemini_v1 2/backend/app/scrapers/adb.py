"""Connecteur ADB (Asian Development Bank) via le standard IATI (d-portal).

ADB publie ses activites au format IATI sous l'identifiant XM-DAC-46004.
On interroge l'API keyless d-portal (endpoint /q, JSON), on ne garde que
les activites ENCORE D'ACTUALITE (statut IATI 1 Pipeline / 2 Implementation)
et on renvoie des Opportunity. Le code de statut IATI numerique est transmis
tel quel dans official_status : official_status.py le traduit en valeur FR
canonique (1->En attente, 2->En cours, 3/4->Termine, 5/6->Annule).

100% ISOLE : toute erreur reseau/parse => liste vide, afin de ne JAMAIS
casser les autres sources du run /scraper/run.
"""
import logging
import requests
from .common import Opportunity

logger = logging.getLogger(__name__)

# Organisation IATI de l'ADB (registre IATI / DAC).
ADB_IATI_REF = "XM-DAC-46004"

# Pays ASEAN couverts (memes que le scraper Banque mondiale).
ASEAN_COUNTRIES = [
    ("KH", "Cambodia"),
    ("VN", "Vietnam"),
    ("TH", "Thailand"),
    ("LA", "Laos"),
    ("MM", "Myanmar"),
    ("ID", "Indonesia"),
    ("PH", "Philippines"),
    ("MY", "Malaysia"),
]

# Codelist IATI activity-status encore d'actualite. On ingere UNIQUEMENT
# ces statuts ; 3 Finalisation / 4 Closed / 5 Cancelled / 6 Suspended sont
# ecartes a la source pour ne pas polluer la carte.
_CURRENT_STATUS = {"1", "2"}


def _activity_url(aid):
    aid = str(aid or "").strip()
    if not aid:
        return "https://d-portal.org/ctrack.html"
    return "https://d-portal.org/ctrack.html#view=act&aid=" + aid


def _parse_activities(rows, country_name):
    """Transforme les lignes d-portal en Opportunity (pur, sans reseau)."""
    items = []
    for a in rows or []:
        try:
            if not isinstance(a, dict):
                continue
            status = str(a.get("status_code") or a.get("status") or "").strip()
            if status not in _CURRENT_STATUS:
                continue
            title = str(a.get("title") or a.get("title_narrative") or "ADB project").strip()
            if not title:
                title = "ADB project"
            aid = a.get("aid") or a.get("iati_identifier") or ""
            parts = [
                str(a.get("title") or ""),
                str(a.get("description") or a.get("description_narrative") or ""),
                "Secteur: " + str(a.get("sector_code") or ""),
                "Periode: " + str(a.get("day_start") or "") + " -> " + str(a.get("day_end") or ""),
            ]
            text = "\n".join(p for p in parts if p and p.strip())
            items.append(Opportunity(
                title=title,
                text=text,
                source="ADB (IATI)",
                source_url=_activity_url(aid),
                funder="ADB",
                country=country_name,
                official_status=status,
            ))
        except Exception as exc:
            logger.warning("ADB IATI: activite ignoree (%s)", exc)
    return items


def _scrape_country(iso2, country_name, limit=10):
    url = "https://d-portal.org/q"
    params = {
        "reporting_ref": ADB_IATI_REF,
        "country_code": iso2,
        "form": "json",
        "limit": limit,
    }
    try:
        data = requests.get(url, params=params, timeout=25).json()
        if isinstance(data, dict):
            rows = (data.get("rows") or data.get("activities")
                    or data.get("results") or [])
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        return _parse_activities(rows, country_name)
    except Exception as exc:
        logger.warning("ADB IATI scraper failed for %s: %s", iso2, exc)
        return []


def scrape_adb_cambodia(limit=25):
    """Point d'entree ADB (nom aligne sur scrape_world_bank_cambodia).

    Couvre l'ASEAN en round-robin ; toute erreur => [] (isole)."""
    try:
        per_country = max(2, min(10, limit // 2))
        buckets = [_scrape_country(iso2, name, per_country)
                   for iso2, name in ASEAN_COUNTRIES]
        interleaved = []
        idx = 0
        while True:
            added = False
            for b in buckets:
                if idx < len(b):
                    interleaved.append(b[idx])
                    added = True
            if not added:
                break
            idx += 1
        return interleaved
    except Exception as exc:
        logger.warning("ADB IATI scrape_adb_cambodia failed: %s", exc)
        return []
