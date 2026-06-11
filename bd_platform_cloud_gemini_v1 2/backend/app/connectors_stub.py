"""
Connecteurs AO (niveau 1 bailleurs multilateraux + niveau 2 portails nationaux).

Niveau 1 (bailleurs) : implementes via l'API publique IATI d-portal
(https://d-portal.org/q, sans cle). On recupere les activites par organisation
declarante (reporting_ref) et pays beneficiaire ASEAN, puis on geocode sur la
capitale du pays (meme principe que le connecteur World Bank). Parsing defensif
(plusieurs noms de colonnes possibles) car le schema d-portal varie.

Niveau 2 (portails e-procurement nationaux) : pas d'API ouverte sans compte ->
stubs honnetes (retournent [] tant qu'un acces officiel n'est pas disponible).

Chaque fonction respecte le contrat fetch() -> list[RawTender].
SOURCES OFFICIELLES / DONNEES IATI UNIQUEMENT — pas d'agregateurs commerciaux.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .common import RawTender, ASEAN_ISO2

# Capitales ASEAN (lat, lng) — geocodage par pays, precision "capital".
_CAPITALS = {
    "KH": (11.5564, 104.9282), "VN": (21.0278, 105.8342),
    "TH": (13.7563, 100.5018), "MM": (16.8409, 96.1735),
    "LA": (17.9757, 102.6331), "ID": (-6.2088, 106.8456),
    "MY": (3.1390, 101.6869), "PH": (14.5995, 120.9842),
    "SG": (1.3521, 103.8198), "BN": (4.9031, 114.9398),
    "TL": (-8.5569, 125.5603),
}

_DPORTAL = "https://d-portal.org/q"
_UA = "Mozilla/5.0 (compatible; ArteliaBD/1.0; +https://bd-projects-map.vercel.app)"


def _http_json(url: str, params: dict[str, Any]) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url + "?" + qs,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _first(row: dict, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", []):
            return v
    return None


def _txt(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v if x)
    return "" if v is None else str(v)


def _date_only(v):
    s = _txt(v).strip()
    return s[:10] if s else None


def _amount(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _dportal_fetch(source_code: str, donor: str, reporting_refs: list[str],
                   per_country: int = 60) -> list[RawTender]:
    out: list[RawTender] = []
    seen: set[str] = set()
    for iso2 in sorted(ASEAN_ISO2):
        latlng = _CAPITALS.get(iso2)
        if not latlng:
            continue
        lat, lng = latlng
        for ref in reporting_refs:
            try:
                payload = _http_json(_DPORTAL, {
                    "form": "json", "from": "act",
                    "reporting_ref": ref, "country_code": iso2,
                    "limit": per_country, "offset": 0,
                })
            except Exception as e:
                print(f"[{source_code}] {iso2}/{ref} fetch error: {e}")
                continue
            rows = payload.get("list") or payload.get("rows") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                aid = _txt(_first(row, "aid", "iati_identifier", "iatiidentifier", "id"))
                if not aid:
                    continue
                key = source_code + "|" + aid
                if key in seen:
                    continue
                seen.add(key)
                title = (_txt(_first(row, "title_narrative", "title", "title_all")) or aid)[:480]
                desc = _txt(_first(row, "description_narrative", "description"))[:2000]
                sector = _txt(_first(row, "sector", "sector_code")) or None
                d_start = _date_only(_first(row, "day_start", "start_planned", "start_actual"))
                d_end = _date_only(_first(row, "day_end", "end_planned", "end_actual"))
                amt = _amount(_first(row, "commitment_usd", "commitment_value", "value_usd"))
                out.append(RawTender(
                    source_code=source_code,
                    external_ref=aid,
                    title=title,
                    country_iso2=iso2,
                    source_url="https://d-portal.org/ctrack.html#view=act&aid=" + urllib.parse.quote(aid),
                    description=desc,
                    sector=sector,
                    procurement_type="development_finance",
                    stage="active" if d_end else "pipeline",
                    value_amount=amt,
                    value_currency="USD" if amt is not None else None,
                    published_at=d_start,
                    deadline_at=d_end,
                    lat=lat, lng=lng, geocode_precision="capital",
                    donor=donor, issuer_name=donor, project_ref=aid,
                    raw={"reporting_ref": ref, "source": "iati/d-portal"},
                ).finalize())
    return out


# ----------------------- Niveau 1 : bailleurs multilateraux -----------------
def adb_fetch() -> list[RawTender]:
    """ADB — activites IATI (Asian Development Bank, reporting org 46004)."""
    return _dportal_fetch("ADB", "Asian Development Bank", ["46004"])


def aiib_fetch() -> list[RawTender]:
    """AIIB — activites IATI (Asian Infrastructure Investment Bank)."""
    return _dportal_fetch("AIIB", "Asian Infrastructure Investment Bank",
                          ["XM-DAC-47137", "47137", "XI-IATI-AIIB"])


def afd_fetch() -> list[RawTender]:
    """AFD — activites IATI (Agence Francaise de Developpement)."""
    return _dportal_fetch("AFD", "Agence Francaise de Developpement",
                          ["FR-3", "XM-DAC-1601", "FR-AFD"])


def jica_fetch() -> list[RawTender]:
    """JICA — activites IATI (Japan International Cooperation Agency)."""
    return _dportal_fetch("JICA", "Japan International Cooperation Agency",
                          ["JP-1", "XM-DAC-2102", "JP-JICA"])


# ----------------------- Niveau 2 : portails e-procurement nationaux --------
# Pas d'API publique ouverte sans compte/cle -> stubs honnetes (0 ligne).
def _todo(source: str, note: str = "") -> list[RawTender]:
    print(f"[{source}] connecteur prepare mais pas d'API ouverte ({note}) -> 0 ligne.")
    return []


def philgeps_fetch() -> list[RawTender]:
    """PHILGEPS (PH) — necessite compte/cle officielle."""
    return _todo("PHILGEPS", "https://www.philgeps.gov.ph")


def gebiz_fetch() -> list[RawTender]:
    """GeBIZ (SG) — pas d'API ouverte."""
    return _todo("GEBIZ", "https://www.gebiz.gov.sg")


def vneps_fetch() -> list[RawTender]:
    """VNEPS / muasamcong (VN) — pas d'API ouverte."""
    return _todo("VNEPS", "https://muasamcong.mpi.gov.vn")


def egp_th_fetch() -> list[RawTender]:
    """e-GP Thailande (GPROCUREMENT) — pas d'API ouverte."""
    return _todo("EGP_TH", "http://process3.gprocurement.go.th")


def myproc_fetch() -> list[RawTender]:
    """ePerolehan (MY) — pas d'API ouverte."""
    return _todo("MYPROC", "https://www.eperolehan.gov.my")


def inaproc_fetch() -> list[RawTender]:
    """INAPROC / LPSE (ID) — pas d'API ouverte unifiee."""
    return _todo("INAPROC", "https://inaproc.lkpp.go.id")


def mef_kh_fetch() -> list[RawTender]:
    """MEF / portail marches publics (KH) — pas d'API ouverte."""
    return _todo("MEF_KH", "https://www.mef.gov.kh")
