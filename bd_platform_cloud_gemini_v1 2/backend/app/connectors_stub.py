from __future__ import annotations

import datetime
import json
import re
import urllib.parse
import urllib.request
from typing import Any

# d-portal encode les dates (day_start/day_end) comme des entiers :
# le nombre de jours ecoules depuis le 1er janvier 1970.
_EPOCH = datetime.date(1970, 1, 1)

from .common import RawTender, ASEAN_ISO2

# Capitales ASEAN (lat, lng) — géocodage par défaut.
# Les flux IATI (d-portal) ne fournissent pas de coordonnées : on place le
# marqueur sur la capitale du pays bénéficiaire (precision = "capital").
_CAPITALS = {
    "KH": (11.5564, 104.9282), "VN": (21.0278, 105.8342), "TH": (13.7563, 100.5018),
    "MM": (16.8409, 96.1735), "LA": (17.9757, 102.6331), "ID": (-6.2088, 106.8456),
    "MY": (3.1390, 101.6869), "PH": (14.5995, 120.9842), "SG": (1.3521, 103.8198),
    "BN": (4.9031, 114.9398), "TL": (-8.5569, 125.5603),
}

_DPORTAL = "http" "s://" "d-portal.org" "/q"
_UA = ("Mozilla/5.0 (compatible; ArteliaBD/1.0; +http" "s://"
       "bd-projects-map.vercel.app)")

# IATI activity status_code -> stage interne.
# Valeurs autorisees par la contrainte ao_tenders_stage_check :
# pipeline | open | closed | awarded | cancelled
_STATUS_STAGE = {
    "1": "pipeline", "2": "execution", "3": "closed", "4": "closed",
    "5": "cancelled", "6": "execution",
}


def _http_json(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", "replace")


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(_txt(x) for x in v if x)
    return str(v)


def _days_to_iso(n: int):
    try:
        return (_EPOCH + datetime.timedelta(days=int(n))).isoformat()
    except (ValueError, OverflowError):
        return None


def _date_only(v: Any):
    # d-portal renvoie un entier (jours depuis 1970-01-01), pas une date ISO.
    # Les colonnes published_at (date) / deadline_at (timestamptz) exigent une
    # date valide : on convertit donc le jour-numero en "YYYY-MM-DD".
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return _days_to_iso(v)
    s = _txt(v).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        return _days_to_iso(s)
    return s[:10]


def _amount(v: Any):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _dportal_fetch(source_code: str, donor: str, reporting_refs: list[str],
                   per_country: int = 150) -> list[RawTender]:
    """Récupère les activités IATI d'un bailleur via d-portal.org/q.

    Schéma vérifié (juin 2026) : réponse {"rows":[...], "count":N}.
    Champs ligne : aid, reporting, reporting_ref, title, description,
    status_code, day_start, day_end, commitment, commitment_eur, slug.
    """
    out: list[RawTender] = []
    seen: set[str] = set()
    for iso2 in sorted(ASEAN_ISO2):
        lat, lng = _CAPITALS.get(iso2, (None, None))
        for ref in reporting_refs:
            try:
                payload = _http_json(_DPORTAL, {
                    "form": "json", "from": "act",
                    "reporting_ref": ref, "country_code": iso2,
                    "limit": per_country, "offset": 0,
                })
            except Exception as exc:  # noqa: BLE001
                print(f"[{source_code}] {iso2}/{ref} fetch error: {exc}")
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
                stage = _STATUS_STAGE.get(status, "open")

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
    print(f"[{source_code}] collected {len(out)} records across ASEAN")
    return out


# --- Connecteurs IATI opérationnels (refs vérifiées sur d-portal.org/q) ---
def adb_fetch() -> list[RawTender]:
    # Banque asiatique de développement — XM-DAC-46004 (~800 activités ASEAN)
    return _dportal_fetch("ADB", "Asian Development Bank", ["XM-DAC-46004"])


def afd_fetch() -> list[RawTender]:
    # Agence Française de Développement — FR-3 (~780 activités ASEAN)
    return _dportal_fetch("AFD", "Agence Francaise de Developpement", ["FR-3"])


# --- Sources sans API ouverte/IATI : stubs honnêtes (renvoient []) ---
def _todo(source: str, note: str = "") -> list[RawTender]:
    print(f"[{source}] connecteur non implemente (pas d'API ouverte). {note}")
    return []


# --- AIIB : connecteur reel (portail officiel, fichier de donnees public) ----
# AIIB ne publie PAS sur IATI/d-portal. En revanche son portail expose, sans
# cle ni authentification, l'integralite de sa liste de projets dans un fichier
# JS statique (`var data=[...]`) consomme par la page projects/list.
_AIIB_HOST = "http" "s://" "www." "aiib.org"
_AIIB_DATA = _AIIB_HOST + "/en/projects/list/.content/all-projects-data.js"

# economy AIIB -> ISO2 (uniquement les pays ASEAN suivis par la carte).
_AIIB_ASEAN = {
    "Indonesia": "ID", "Malaysia": "MY", "Philippines": "PH",
    "Viet Nam": "VN", "Vietnam": "VN", "Cambodia": "KH",
    "Lao PDR": "LA", "Laos": "LA", "Thailand": "TH",
    "Singapore": "SG", "Myanmar": "MM", "Brunei": "BN",
    "Brunei Darussalam": "BN", "Timor-Leste": "TL", "Timor Leste": "TL",
}

# statut AIIB -> stage interne (contrainte ao_tenders_stage_check).
_AIIB_STAGE = {
    "Proposed": "pipeline", "Approved": "awarded",
    "Terminated / Cancelled": "cancelled", "Dropped": "cancelled",
}


def _parse_js_array(text: str) -> list[dict]:
    """Extrait le tableau d'objets du fichier AIIB `var data=[ {..}, .. ];`.

    Le fichier se termine par une virgule traînante et un element vide :
    on isole entre le premier '[' et le dernier ']', puis on nettoie la
    virgule finale avant de parser en JSON.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return []
    cleaned = "[" + text[start + 1:end] + "]"
    cleaned = re.sub(r",(\s*)\]", r"\1]", cleaned)   # virgule traînante
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[AIIB] parse error: {exc}")
        return []
    return data if isinstance(data, list) else []


def _aiib_amount(*vals: Any):
    """Parse les montants AIIB du type 'USD120 million' / 'USD4.7 million'."""
    for v in vals:
        s = _txt(v)
        m = re.search(r"USD\s*([\d,.]+)\s*million", s, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", "")) * 1_000_000.0, "USD"
            except ValueError:
                continue
    return None, None


def aiib_fetch() -> list[RawTender]:
    """Banque asiatique d'investissement pour les infrastructures (AIIB).

    Source : fichier projets public du portail officiel (sans cle). On filtre
    les economies ASEAN. Geocodage = capitale du pays (AIIB ne fournit pas de
    coordonnees). published_at = annee d'approbation (precision annuelle).
    """
    try:
        text = _http_text(_AIIB_DATA)
    except Exception as exc:  # noqa: BLE001
        print(f"[AIIB] fetch error: {exc}")
        return []
    rows = _parse_js_array(text)
    out: list[RawTender] = []
    seen: set[str] = set()
    for p in rows:
        economy = _txt(p.get("economy")).strip()
        iso2 = _AIIB_ASEAN.get(economy)
        if not iso2 or iso2 not in ASEAN_ISO2:
            continue
        path = _txt(p.get("path")).strip()
        name = _txt(p.get("name")).strip()
        ext_id = path or name
        if not ext_id or ext_id in seen:
            continue
        seen.add(ext_id)

        status = _txt(p.get("status")).strip()
        stage = _AIIB_STAGE.get(status, "closed")
        amt, cur = _aiib_amount(
            p.get("proposed_funding"), p.get("approved_funding"),
            p.get("committed_funding"), p.get("special_funding"),
        )
        year = _txt(p.get("date")).strip()
        published = f"{year}-01-01" if year.isdigit() and len(year) == 4 else None
        lat, lng = _CAPITALS.get(iso2, (None, None))
        url = (_AIIB_HOST + path) if path.startswith("/") else (path or _AIIB_DATA)
        sector = _txt(p.get("sector")).strip() or None

        out.append(RawTender(
            "AIIB", ext_id, name or ext_id, iso2, url,
            description="",
            sector=sector,
            procurement_type="development_finance",
            stage=stage,
            value_amount=amt,
            value_currency=cur,
            published_at=published,
            deadline_at=None,
            lat=lat, lng=lng,
            geocode_precision="capital",
            donor="Asian Infrastructure Investment Bank",
            issuer_name=None,
            project_ref=ext_id,
            language="en",
            raw={
                "economy": economy,
                "status": status,
                "financing_type": p.get("financing_type"),
                "date": year,
            },
        ).finalize())
    print(f"[AIIB] collected {len(out)} records across ASEAN")
    return out


def jica_fetch() -> list[RawTender]:
    # Agence japonaise de cooperation internationale — XM-DAC-701-8 (IATI depuis 2014)
    return _dportal_fetch("JICA", "Japan International Cooperation Agency", ["XM-DAC-701-8"])


def philgeps_fetch() -> list[RawTender]:
    return _todo("PHILGEPS", "www.philgeps.gov.ph (pas d'API publique)")


def gebiz_fetch() -> list[RawTender]:
    return _todo("GEBIZ", "www.gebiz.gov.sg (authentification requise)")


def vneps_fetch() -> list[RawTender]:
    return _todo("VNEPS", "muasamcong.mpi.gov.vn (pas d'API publique)")


def egp_th_fetch() -> list[RawTender]:
    return _todo("EGP_TH", "process3.gprocurement.go.th (pas d'API publique)")


def myproc_fetch() -> list[RawTender]:
    return _todo("MYPROC", "www.eperolehan.gov.my (authentification requise)")


def inaproc_fetch() -> list[RawTender]:
    return _todo("INAPROC", "inaproc.lkpp.go.id (pas d'API publique)")


def mef_kh_fetch() -> list[RawTender]:
    return _todo("MEF_KH", "www.mef.gov.kh (pas d'API publique)")
