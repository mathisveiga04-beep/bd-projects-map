"""Connecteur IATI generique (d-portal).

Contrairement au connecteur ADB (qui filtre sur reporting_ref=XM-DAC-46004),
celui-ci interroge d-portal PAR PAYS sans filtrer sur l'organisme : il capte
donc automatiquement TOUS les publieurs IATI actifs dans la region (Banque
mondiale, AIIB, IFC, JICA, AFD, KfW, BID, GCF, UE, agences bilaterales...).

Regles :
- ne garde que les statuts courants (IATI activity-status 1 Pipeline / 2 Implementation) ;
- pre-filtre "physique" (mots-cles construction / infrastructure / batiment) pour ne
  pas noyer le pipeline ni le quota Gemini sous des projets hors sujet ;
- ignore l'ADB (deja couvert par le connecteur dedie, evite le double traitement) ;
- totalement isole : toute erreur reseau/parse renvoie une liste vide, jamais d'exception.
"""

import logging

from .common import Opportunity

logger = logging.getLogger(__name__)

# Pays ASEAN (iso2, nom), identiques au connecteur ADB.
ASEAN_COUNTRIES = [
    ("KH", "Cambodia"), ("VN", "Vietnam"), ("TH", "Thailand"),
    ("LA", "Laos"), ("MM", "Myanmar"), ("ID", "Indonesia"),
    ("PH", "Philippines"), ("MY", "Malaysia"),
]

# IATI activity-status consideres comme "en cours".
_CURRENT_STATUS = {"1", "2"}

# ADB : deja couvert par scrapers/adb.py ; on l'exclut ici pour ne pas traiter deux fois.
_ADB_REF = "XM-DAC-46004"

# Correspondances identifiant IATI -> nom lisible (seulement les surs ; sinon on
# retombe sur le nom d'organisation fourni par d-portal, puis sur l'identifiant brut).
_FUNDER_BY_REF = {
    _ADB_REF: "ADB",
}

# Mots-cles "projet physique" (construction / infrastructure / batiment).
_RELEVANT_KW = (
    "construction", "infrastructure", "road", "highway", "bridge", "hospital",
    "clinic", "school", "university", "housing", "urban", "water supply",
    "sanitation", "sewerage", "power plant", "energy", "electricity", "grid",
    "railway", "metro", "airport", "seaport", "terminal", "facility",
    "rehabilitation", "reconstruction", "renovation", "civil works",
    "transport", "irrigation", "dam", "building construction",
)


def _funder(ref, name):
    ref = (ref or "").strip()
    name = (name or "").strip()
    if ref in _FUNDER_BY_REF:
        return _FUNDER_BY_REF[ref]
    return name or ref or "IATI"


def _is_relevant(blob):
    b = (blob or "").lower()
    return any(kw in b for kw in _RELEVANT_KW)


def _activity_url(aid):
    aid = (aid or "").strip()
    if not aid:
        return "https://d-portal.org/ctrack.html"
    return "https://d-portal.org/ctrack.html#view=act&aid=" + aid


def _parse_activities(rows, country_name):
    out = []
    for a in (rows or []):
        try:
            if not isinstance(a, dict):
                continue
            ref = str(a.get("reporting_ref") or a.get("reporting") or "").strip()
            if ref == _ADB_REF:
                continue  # couvert par le connecteur ADB dedie
            status = str(a.get("status_code") or a.get("status") or "").strip()
            if status not in _CURRENT_STATUS:
                continue
            title = str(a.get("title") or a.get("title_narrative") or "").strip()
            if not title:
                continue
            desc = str(a.get("description") or a.get("description_narrative") or "").strip()
            sector = str(a.get("sector") or a.get("sector_code") or "").strip()
            name = str(a.get("reporting_org") or a.get("reporting_org_narrative") or a.get("reporting") or "").strip()
            if not _is_relevant(title + " " + desc + " " + sector):
                continue
            parts = [title, desc]
            if sector:
                parts.append("Secteur: " + sector)
            text = "\n".join([p for p in parts if p])
            aid = str(a.get("aid") or a.get("iati_identifier") or "").strip()
            funder = _funder(ref, name)
            out.append(Opportunity(
                title=title,
                text=text,
                source="IATI (" + funder + ")",
                source_url=_activity_url(aid),
                funder=funder,
                country=country_name,
                official_status=status,
            ))
        except Exception as e:
            logger.warning("IATI parse item error: %s", e)
            continue
    return out


def _scrape_country(iso2, country_name, limit=40):
    import requests  # import paresseux : requests absent de l'env CI (pytest seul)
    try:
        resp = requests.get(
            "https://d-portal.org/q",
            params={"country_code": iso2, "form": "json", "limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("activities") or data.get("results") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        return _parse_activities(rows, country_name)
    except Exception as e:
        logger.warning("IATI scrape %s error: %s", iso2, e)
        return []


def scrape_iati_sea(limit_per_country=40):
    """Balaye les 8 pays ASEAN sur d-portal, tous publieurs IATI confondus."""
    out = []
    for iso2, name in ASEAN_COUNTRIES:
        try:
            out.extend(_scrape_country(iso2, name, limit=limit_per_country))
        except Exception as e:
            logger.warning("IATI country %s error: %s", iso2, e)
            continue
    return out
