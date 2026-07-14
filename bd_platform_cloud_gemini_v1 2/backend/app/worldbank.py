"""
Connecteur Banque Mondiale (source 'WB', bailleur, multi-pays).

Projects API : https://search.worldbank.org/api/v3/projects (JSON)
-> projets finances par la WB, avec secteur, montant, statut, pays.

NOTE : la fonction fetch() fait des appels reseau (a executer sur le backend
Render qui a acces internet). Les fonctions parse_*() sont pures et testables
hors-ligne sur des payloads d'exemple.
"""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
from typing import Any, Iterable

from .common import RawTender, ASEAN_ISO2
from .stage_map import map_wb_stage

SOURCE_CODE = "WB"
PROJECTS_API = "https://search.worldbank.org/api/v3/projects"

# WB country codes (ISO3) -> ISO2 pour les 11 pays ASEAN.
# IMPORTANT : l'API World Bank attend des codes ISO2 dans countrycode_exact
# (ex. "VN" -> 331 projets, "VNM" -> 0). On interroge donc avec la valeur ISO2.
WB_ISO3_TO_ISO2 = {
    "BRN": "BN", "KHM": "KH", "IDN": "ID", "LAO": "LA", "MYS": "MY",
    "MMR": "MM", "PHL": "PH", "SGP": "SG", "THA": "TH", "VNM": "VN", "TLS": "TL",
}

# Ensemble des ISO2 ASEAN cibles (pour valider la valeur renvoyee par l'API).
WB_ISO2 = set(WB_ISO3_TO_ISO2.values())

# Coordonnees de repli par pays (centroides capitales) pour geocode_precision='country'
COUNTRY_CENTROID = {
    "BN": (4.9031, 114.9398), "KH": (11.5564, 104.9282), "ID": (-6.2088, 106.8456),
    "LA": (17.9757, 102.6331), "MY": (3.1390, 101.6869), "MM": (16.8409, 96.1735),
    "PH": (14.5995, 120.9842), "SG": (1.3521, 103.8198), "TH": (13.7563, 100.5018),
    "VN": (21.0278, 105.8342), "TL": (-8.5569, 125.5603),
}

def _http_json(url: str, params: dict[str, Any]) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}"
    req = urllib.request.Request(full, headers={
        "User-Agent": "MVE-ProjectIntelligenceMap/1.0 (BD tender aggregator; contact: mve)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch(rows_per_country: int = 200) -> list[RawTender]:
    """Recupere les projets WB des 11 pays ASEAN. (Reseau : backend Render.)"""
    out: list[RawTender] = []
    fields = ",".join([
        "id", "project_name", "countryshortname", "countrycode",
        "sector", "boardapprovaldate", "totalcommamount",
        "projectstatusdisplay", "url", "regionname",
    ])
    for iso3, iso2 in WB_ISO3_TO_ISO2.items():
        try:
            # L'API attend l'ISO2 (ex. "VN"), pas l'ISO3 (ex. "VNM").
            data = _http_json(PROJECTS_API, {
                "format": "json", "countrycode_exact": iso2,
                "rows": rows_per_country, "fl": fields,
            })
            out.extend(parse_projects(data, iso2))
        except Exception as e:  # un pays en echec n'arrete pas les autres
            print(f"[WB] {iso2} fetch error: {e}")
    return out

def _country_code_iso2(value: Any) -> str:
    """Normalise le champ countrycode (str OU liste ['VN']) en ISO2 majuscule."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").upper()

def parse_projects(payload: dict, iso2_hint: str | None = None) -> list[RawTender]:
    """Transforme la reponse Projects API en RawTender (pur, testable)."""
    projects = payload.get("projects") or {}
    # l'API renvoie soit un dict {id: {...}}, soit une liste
    items: Iterable[dict]
    if isinstance(projects, dict):
        items = projects.values()
    else:
        items = projects

    results: list[RawTender] = []
    for p in items:
        iso2 = iso2_hint
        cc = _country_code_iso2(p.get("countrycode"))
        if cc in WB_ISO2:
            iso2 = cc
        if iso2 not in ASEAN_ISO2:
            continue

        sector = _sector_str(p.get("sector"))
        url = p.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{p.get('id','')}"
        amount = _to_float(p.get("totalcommamount"))
        lat, lng, prec = _geocode_country(iso2)

        ext = str(p.get("id") or "")
        rt = RawTender(
            source_code=SOURCE_CODE,
            external_ref=ext,
            source_id=ext,
            title=p.get("project_name") or "(sans titre)",
            description=sector,
            country_iso2=iso2,
            country_name=p.get("countryshortname"),
            source_url=url,
            sector=sector,
            procurement_type="project_financing",
            stage=_map_stage(p.get("projectstatusdisplay")),
            value_amount=amount,
            value_currency="USD" if amount else None,
            published_at=_date_only(p.get("boardapprovaldate")),
            location_text=p.get("countryshortname"),
            lat=lat, lng=lng, geocode_precision=prec,
            # parties -> alimentent le graphe relationnel
            donor="World Bank",
            stage=("execution" if (p.get("projectstatusdisplay") or "").strip().lower() == "active" else (p.get("projectstatusdisplay") or "")),
            project_name=p.get("project_name") or None,
            project_ref=ext,
            raw=p,
        ).finalize()
        results.append(rt)
    return results

def _sector_str(sector_field: Any) -> str:
    if not sector_field:
        return ""
    if isinstance(sector_field, list):
        names = []
        for s in sector_field:
            if isinstance(s, dict):
                names.append(s.get("Name") or s.get("name") or "")
            else:
                names.append(str(s))
        return ", ".join(n for n in names if n)
    if isinstance(sector_field, dict):
        return sector_field.get("Name") or sector_field.get("name") or ""
    return str(sector_field)

def _to_float(v: Any) -> float | None:
    if v in (None, "", "0"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None

def _date_only(v: Any) -> str | None:
    if not v:
        return None
    return str(v)[:10]

def _map_stage(status: Any) -> str:
    # Delegue a stage_map (source unique de verite, couverte par tests).
    return map_wb_stage(status)

def _geocode_country(iso2: str):
    c = COUNTRY_CENTROID.get(iso2)
    if c:
        return c[0], c[1], "country"
    return None, None, "none"
