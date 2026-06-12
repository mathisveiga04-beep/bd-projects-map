from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .common import RawTender, ASEAN_ISO2

# Capitales ASEAN (lat, lng) - geocodage par defaut.
# Les flux IATI (d-portal) ne fournissent pas de coordonnees : on place le
# marqueur sur la capitale du pays beneficiaire (precision = "capital").
_CAPITALS = {
    "KH": (11.5564, 104.9282), "VN": (21.0278, 105.8342), "TH": (13.7563, 100.5018),
    "MM": (16.8409, 96.1735), "LA": (17.9757, 102.6331), "ID": (-6.2088, 106.8456),
    "MY": (3.1390, 101.6869), "PH": (14.5995, 120.9842), "SG": (1.3521, 103.8198),
    "BN": (4.9031, 114.9398), "TL": (-8.5569, 125.5603),
}

_DPORTAL = "https://d-portal.org/q"
_UA = "Mozilla/5.0 (compatible; ArteliaBD/1.0; +https://bd-projects-map.vercel.app)"

# IATI activity status_code -> stage interne
_STATUS_STAGE = {
    "1": "pipeline", "2": "active", "3": "closed", "4": "closed",
    "5": "cancelled", "6": "suspended",
}


def _http_json(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(_txt(x) for x in v if x)
    return str(v)


def _date_only(v: Any):
    s = _txt(v).strip()
    return s[:10] if s else None


def _amount(v: Any):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _dportal_fetch(source_code: str, donor: str, reporting_refs: list,
                   per_country: int = 150) -> list:
    """Recupere les activites IATI d'un bailleur via d-portal.org/q.

    Schema verifie (juin 2026) : reponse {"rows":[...], "count":N}.
    Champs ligne : aid, reporting, reporting_ref, title, description,
    status_code, day_start, day_end, commitment, commitment_eur, slug.
    """
    out = []
    seen = set()
    for iso2 in sorted(ASEAN_ISO2):
        lat, lng = _CAPITALS.get(iso2, (None, None))
        for ref in reporting_refs:
            try:
                payload = _http_json(_DPORTAL, {
                    "form": "json", "from": "act",
                    "reporting_ref": ref, "country_code": iso2,
                    "limit": per_country, "offset": 0,
                })
            except Exception as exc:
                print("[" + source_code + "] " + iso2 + "/" + ref + " fetch error: " + str(exc))
                continue
            rows = payload.get("rows") or payload.get("list") or []
            for row in rows:
                aid = _txt(row.get("aid") or row.get("iati_identifier")
                           or row.get("slug")).strip()
                if not aid:
                    continue
                key = source_code + "|" + aid
                if key in seen:
                    continue
                seen.add(key)

                title = _txt(row.get("title")).strip() or aid
                desc = _txt(row.get("description")).strip()
                status = _txt(row.get("status_code")).strip()
                stage = _STATUS_STAGE.get(status, "active")

                amt_eur = _amount(row.get("commitment_eur"))
                amt = amt_eur or _amount(row.get("commitment"))
                cur = "EUR" if amt_eur else None

                d_start = _date_only(row.get("day_start"))
                d_end = _date_only(row.get("day_end"))
                rep_name = _txt(row.get("reporting")).strip() or donor
                url = (_DPORTAL.replace("/q", "/ctrack.html")
                       + "#view=act&aid=" + urllib.parse.quote(aid))

                out.append(RawTender(
                    source_code, aid, title, iso2, url,
                    description=desc,
                    sector=None,
                    procurement_type="development_finance",
                    stage=stage,
                    value_amount=amt,
                    value_currency=cur,
                    published_at=d_start,
                    deadline_at=d_end,
                    lat=lat, lng=lng,
                    geocode_precision="capital",
                    donor=donor,
                    issuer_name=rep_name,
                    project_ref=aid,
                    language="en",
                    raw={
                        "reporting_ref": ref,
                        "status_code": status,
                        "commitment_eur": row.get("commitment_eur"),
                    },
                ).finalize())
    print("[" + source_code + "] collected " + str(len(out)) + " records across ASEAN")
    return out


# --- Connecteurs IATI operationnels (refs verifiees sur d-portal.org/q) ---
def adb_fetch() -> list:
    # Banque asiatique de developpement - XM-DAC-46004 (~800 activites ASEAN)
    return _dportal_fetch("ADB", "Asian Development Bank", ["XM-DAC-46004"])


def afd_fetch() -> list:
    # Agence Francaise de Developpement - FR-3 (~780 activites ASEAN)
    return _dportal_fetch("AFD", "Agence Francaise de Developpement", ["FR-3"])


# --- Sources sans API ouverte/IATI : stubs honnetes (renvoient []) ---
def _todo(source: str, note: str = "") -> list:
    print("[" + source + "] connecteur non implemente (pas d'API ouverte). " + note)
    return []


def aiib_fetch() -> list:
    # AIIB ne publie aucune activite sur IATI/d-portal -> portail propre requis.
    return _todo("AIIB", "https://www.aiib.org/en/projects/list/index.html (pas de flux IATI)")


def jica_fetch() -> list:
    # JICA ne publie pas sur IATI/d-portal -> source ODA japonaise distincte requise.
    return _todo("JICA", "https://www.jica.go.jp (pas de flux IATI d-portal)")


def philgeps_fetch() -> list:
    return _todo("PHILGEPS", "https://www.philgeps.gov.ph (pas d'API publique)")


def gebiz_fetch() -> list:
    return _todo("GEBIZ", "https://www.gebiz.gov.sg (authentification requise)")


def vneps_fetch() -> list:
    return _todo("VNEPS", "https://muasamcong.mpi.gov.vn (pas d'API publique)")


def egp_th_fetch() -> list:
    return _todo("EGP_TH", "http://process3.gprocurement.go.th (pas d'API publique)")


def myproc_fetch() -> list:
    return _todo("MYPROC", "https://www.eperolehan.gov.my (authentification requise)")


def inaproc_fetch() -> list:
    return _todo("INAPROC", "https://inaproc.lkpp.go.id (pas d'API publique)")


def mef_kh_fetch() -> list:
    return _todo("MEF_KH", "https://www.mef.gov.kh (pas d'API publique)")
