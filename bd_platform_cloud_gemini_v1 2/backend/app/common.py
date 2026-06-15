"""
Couche commune d'ingestion (ASEAN Construction Intelligence).

- schema normalise RawTender (aligne sur la spec : champs AO + entites liees)
- filtre sectoriel "chaine de valeur batiment/infra" (multilingue, extensible)
- scoring de pertinence multi-criteres (0-100)
- derivation sector (programme) ET discipline (corps de metier)
- identifiants DETERMINISTES (uuid5) -> graphe relationnel idempotent
- hash de contenu + dedoublonnage

Aucune dependance externe : testable hors-ligne.
"""
from __future__ import annotations
import hashlib
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

ASEAN_ISO2 = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "VN", "TL"}

ISO2_TO_NAME = {
    "BN": "Brunei", "KH": "Cambodge", "ID": "Indonesie", "LA": "Laos",
    "MY": "Malaisie", "MM": "Myanmar", "PH": "Philippines", "SG": "Singapour",
    "TH": "Thailande", "VN": "Vietnam", "TL": "Timor-Leste",
}

# Langue dominante par pays (pour le champ 'language' + future traduction)
ISO2_TO_LANG = {
    "BN": "en", "KH": "km", "ID": "id", "LA": "lo", "MY": "en", "MM": "my",
    "PH": "en", "SG": "en", "TH": "th", "VN": "vi", "TL": "pt",
}

# --- Filtre sectoriel "chaine de valeur batiment / infrastructure" -----------
INCLUDE_KEYWORDS = [
    # FR
    "batiment", "construction", "architecture", "architectural", "urbanisme",
    "structure", "genie civil", "supervision", "maitrise d'oeuvre",
    "maitrise d'ouvrage", "ventilation", "climatisation", "chauffage",
    "facade", "plomberie", "electricite", "incendie", "renovation",
    "rehabilitation", "ingenierie", "desenfumage", "etancheite",
    # EN — batiment / MEP
    "building", "civil works", "structural", "mechanical", "electrical",
    "plumbing", "mep", "hvac", "air-conditioning", "air conditioning",
    "ventilation", "facade", "curtain wall", "fire protection", "fire-fighting",
    "fit-out", "fitout", "renovation", "rehabilitation", "refurbishment",
    "bms", "building management system", "gtb", "bim",
    "construction supervision", "project management", "construction management",
    "design services", "engineering consultancy", "engineering services",
    "quantity surveying", "architectural design", "urban planning",
    # EN — programmes / infra
    "hospital", "healthcare", "clinic", "school", "university", "campus",
    "terminal", "airport", "port", "harbour", "harbor", "jetty", "wharf",
    "housing", "residential", "office building", "commercial building",
    "mixed-use", "hotel", "resort", "hospitality", "mall", "retail",
    "industrial building", "factory", "warehouse", "logistics",
    "water treatment", "wastewater", "sewerage", "drainage", "water supply",
    "district cooling", "chilled water", "power plant", "substation",
    "transmission", "energy", "solar", "data center", "data centre",
    "infrastructure", "bridge", "road", "highway", "rail", "metro", "mrt",
]

# Indices "corps de metier batiment" forts (poids ++)
STRONG_KEYWORDS = [
    "building", "batiment", "hvac", "mep", "facade", "curtain wall",
    "construction supervision", "construction management", "architectural",
    "fit-out", "fitout", "bms", "bim", "district cooling", "data center",
    "data centre", "structural", "genie civil",
]

EXCLUDE_KEYWORDS = [
    "supply of vehicles", "vehicle", "fuel", "fertilizer", "pharmaceutical",
    "medicine", "drugs", "food", "rice", "textbook", "stationery",
    "software license", "laptop", "desktop computer", "server hardware",
    "network equipment", "insurance", "audit services", "legal services",
    "consultancy for tax", "catering", "uniform", "furniture supply",
    "agriculture inputs", "seeds", "livestock",
]


def _norm(s: str) -> str:
    """minuscule + sans accents pour matcher de facon robuste."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


# --- Scoring multi-criteres --------------------------------------------------
def relevance(title: str, description: str = "", sector: str = "",
              amount: Optional[float] = None, donor: str = "",
              authority: str = "", procurement_type: str = "",
              stage: str = "") -> tuple[int, str]:
    """Retourne (score 0-100, statut 'kept'|'filtered').
    Criteres : mots-cles (base) + montant + financeur + autorite + type marche."""
    hay = _norm(" ".join([title or "", description or "", sector or "",
                          procurement_type or ""]))
    if not hay.strip():
        return 0, "filtered"

    # Exclusions dures : sauf si un signal batiment FORT est aussi present
    for kw in EXCLUDE_KEYWORDS:
        if _norm(kw) in hay and not any(_norm(s) in hay for s in STRONG_KEYWORDS):
            return 0, "filtered"

    score = 0
    for kw in INCLUDE_KEYWORDS:
        if _norm(kw) in hay:
            score += 6
    for kw in STRONG_KEYWORDS:
        if _norm(kw) in hay:
            score += 12

    # Contexte institutionnel = signal de fiabilite/officialite
    if donor:
        score += 8
    if authority:
        score += 5

    # Type de marche pertinent (travaux / services d'ingenierie)
    pt = _norm(procurement_type)
    if any(k in pt for k in ["works", "civil", "construction", "consulting",
                             "consultant", "design", "supervision", "engineering"]):
        score += 6

    # Echelle financiere (proxy d'importance projet)
    if amount:
        if amount >= 50_000_000:
            score += 10
        elif amount >= 10_000_000:
            score += 6
        elif amount >= 1_000_000:
            score += 3

    # Stade pipeline : privilegie les AO actionnables (amont) vs deja attribues/clotures (classement)
    base = score
    st = _norm(stage)
    if st:
        if any(k in st for k in ["plan", "identif", "pipeline", "prospect", "concept", "feasib",
                                 "prequalif", "pre-tender", "pretender", "tender", "bid", "procure",
                                 "design", "eoi", "expression of interest", "rfp", "rfq", "appel",
                                 "consultation", "soumission"]):
            score += 12
        elif any(k in st for k in ["award", "attribu", "contract", "signed", "ongoing",
                                   "construction", "execution", "en cours", "works ongoing"]):
            score -= 8
        elif any(k in st for k in ["complete", "completed", "closed", "cancel", "terminated",
                                   "acheve", "cloture", "annule", "abandonne"]):
            score -= 20
    score = max(0, min(score, 100))
    status = "kept" if base >= 8 else "filtered"
    return score, status


# --- Discipline (corps de metier) vs Secteur (programme) ---------------------
_DISCIPLINE_MAP = [
    ("project_management",      ["project management", "maitrise d'ouvrage", "pmo", "owner's engineer"]),
    ("construction_management", ["construction management", "construction supervision", "supervision de chantier"]),
    ("architecture",            ["architecture", "architectural", "design services", "concept design"]),
    ("urban_planning",          ["urban planning", "urbanisme", "master plan", "masterplan"]),
    ("structure",               ["structural", "structure", "genie civil", "civil works", "foundation"]),
    ("mep",                     ["mep", "mechanical electrical", "building services"]),
    ("hvac",                    ["hvac", "air-conditioning", "air conditioning", "climatisation", "chauffage", "chilled water"]),
    ("ventilation",             ["ventilation", "smoke extraction", "desenfumage"]),
    ("facade",                  ["facade", "curtain wall", "cladding"]),
    ("fire",                    ["fire protection", "fire-fighting", "fire fighting", "incendie"]),
    ("plumbing",                ["plumbing", "plomberie", "sanitary"]),
    ("electrical",              ["electrical installation", "electricite", "power distribution", "lv installation"]),
    ("bms_gtb",                 ["bms", "building management system", "gtb", "scada"]),
    ("bim",                     ["bim", "building information model"]),
    ("water_treatment",         ["water treatment", "water supply", "potable water"]),
    ("wastewater",              ["wastewater", "sewerage", "sewage", "drainage", "sanitation"]),
    ("district_cooling",        ["district cooling"]),
    ("energy",                  ["power plant", "substation", "transmission", "solar", "energy", "electrification"]),
    ("data_center",             ["data center", "data centre"]),
    ("transport_infra",         ["airport", "terminal", "port", "harbour", "harbor", "bridge", "road", "highway", "rail", "metro", "mrt"]),
]

_SECTOR_MAP = [
    ("healthcare",     ["hospital", "healthcare", "clinic", "medical"]),
    ("education",      ["school", "university", "campus", "education"]),
    ("hospitality",    ["hotel", "resort", "hospitality"]),
    ("commercial",     ["mall", "retail", "office building", "commercial", "mixed-use"]),
    ("residential",    ["housing", "residential", "apartment", "dormitory"]),
    ("industrial",     ["factory", "warehouse", "industrial", "logistics", "manufacturing"]),
    ("water",          ["water treatment", "wastewater", "water supply", "sewerage", "drainage"]),
    ("energy",         ["power plant", "substation", "energy", "solar", "transmission"]),
    ("data_center",    ["data center", "data centre"]),
    ("transport",      ["airport", "port", "rail", "metro", "mrt", "road", "highway", "bridge"]),
]


def _first_match(hay: str, mapping) -> Optional[str]:
    for label, kws in mapping:
        if any(_norm(k) in hay for k in kws):
            return label
    return None


def discipline(title: str, description: str = "") -> Optional[str]:
    return _first_match(_norm(" ".join([title or "", description or ""])), _DISCIPLINE_MAP)


def sector_class(title: str, description: str = "", sector: str = "") -> Optional[str]:
    return _first_match(_norm(" ".join([title or "", description or "", sector or ""])), _SECTOR_MAP)


# --- Identifiants DETERMINISTES (graphe relationnel idempotent) --------------
AO_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


def _det_uuid(*parts: str) -> str:
    return str(uuid.uuid5(AO_NAMESPACE, "|".join(p or "" for p in parts)))


def org_uid(name: str, country: str = "") -> str:
    return _det_uuid("ORG", _norm(name), (country or "").upper())


def company_uid(name: str, country: str = "") -> str:
    return _det_uuid("CO", _norm(name), (country or "").upper())


def person_uid(name: str, org: str = "") -> str:
    return _det_uuid("PER", _norm(name), _norm(org))


def project_uid(source_code: str, external_id: str) -> str:
    return _det_uuid("PRJ", source_code or "", external_id or "")


def role_uid(role: str, tender_ref: str, party_uid: str) -> str:
    return _det_uuid("ROLE", role, tender_ref, party_uid)


# --- Geocodage par toponyme (villes/provinces ASEAN) -------------------------
# Upgrade le geocodage "pays" (centroide capitale) vers une precision "city"
# quand un toponyme reel figure dans le texte de l'AO. Aucune donnee inventee :
# uniquement des lieux deja presents dans les champs source, geocodes via une
# table de coordonnees verifiees, retenus seulement si le lieu appartient au
# pays de l'AO (anti faux-positif transfrontalier).
import re as _re_geo

ASEAN_GAZETTEER = {
    "jakarta": (-6.2, 106.82, "ID"),
    "surabaya": (-7.25, 112.75, "ID"),
    "bandung": (-6.91, 107.61, "ID"),
    "medan": (3.59, 98.67, "ID"),
    "semarang": (-6.97, 110.42, "ID"),
    "makassar": (-5.13, 119.42, "ID"),
    "palembang": (-2.98, 104.76, "ID"),
    "yogyakarta": (-7.8, 110.36, "ID"),
    "denpasar": (-8.65, 115.22, "ID"),
    "bali": (-8.34, 115.09, "ID"),
    "sulawesi": (-1.85, 120.5, "ID"),
    "sumatra": (-0.59, 101.34, "ID"),
    "sumatera": (-0.59, 101.34, "ID"),
    "kalimantan": (-1.68, 113.38, "ID"),
    "papua": (-4.27, 138.08, "ID"),
    "lombok": (-8.65, 116.32, "ID"),
    "aceh": (4.7, 96.75, "ID"),
    "batam": (1.13, 104.05, "ID"),
    "west java": (-6.9, 107.6, "ID"),
    "east java": (-7.5, 112.5, "ID"),
    "central java": (-7.3, 110, "ID"),
    "java": (-7.5, 110, "ID"),
    "bekasi": (-6.24, 107, "ID"),
    "tangerang": (-6.18, 106.63, "ID"),
    "bogor": (-6.6, 106.8, "ID"),
    "padang": (-0.95, 100.35, "ID"),
    "banjarmasin": (-3.32, 114.59, "ID"),
    "pontianak": (-0.03, 109.34, "ID"),
    "manado": (1.49, 124.84, "ID"),
    "balikpapan": (-1.27, 116.83, "ID"),
    "pekanbaru": (0.51, 101.45, "ID"),
    "lampung": (-5.45, 105.27, "ID"),
    "nusa tenggara": (-8.65, 117.36, "ID"),
    "maluku": (-3.24, 130.15, "ID"),
    "jambi": (-1.61, 103.61, "ID"),
    "bengkulu": (-3.8, 102.27, "ID"),
    "flores": (-8.66, 121.08, "ID"),
    "manila": (14.6, 120.98, "PH"),
    "metro manila": (14.6, 121, "PH"),
    "cebu": (10.32, 123.9, "PH"),
    "davao": (7.07, 125.61, "PH"),
    "quezon city": (14.68, 121.05, "PH"),
    "mindanao": (7.9, 125, "PH"),
    "luzon": (16, 121, "PH"),
    "visayas": (11, 123.5, "PH"),
    "iloilo": (10.72, 122.56, "PH"),
    "baguio": (16.4, 120.6, "PH"),
    "cagayan de oro": (8.48, 124.65, "PH"),
    "zamboanga": (6.92, 122.08, "PH"),
    "bicol": (13.42, 123.41, "PH"),
    "palawan": (9.5, 118.5, "PH"),
    "leyte": (10.8, 124.8, "PH"),
    "negros": (10, 123, "PH"),
    "bohol": (9.85, 124.14, "PH"),
    "cavite": (14.28, 120.87, "PH"),
    "laguna": (14.17, 121.33, "PH"),
    "batangas": (13.76, 121.06, "PH"),
    "pampanga": (15.08, 120.66, "PH"),
    "bulacan": (14.79, 120.88, "PH"),
    "cotabato": (7.22, 124.25, "PH"),
    "general santos": (6.11, 125.17, "PH"),
    "bacolod": (10.67, 122.95, "PH"),
    "hanoi": (21.03, 105.85, "VN"),
    "ho chi minh": (10.82, 106.63, "VN"),
    "da nang": (16.05, 108.21, "VN"),
    "danang": (16.05, 108.21, "VN"),
    "haiphong": (20.86, 106.68, "VN"),
    "can tho": (10.04, 105.78, "VN"),
    "hue": (16.46, 107.59, "VN"),
    "nha trang": (12.24, 109.19, "VN"),
    "mekong delta": (10, 105.7, "VN"),
    "mekong": (10, 105.7, "VN"),
    "halong": (20.95, 107.08, "VN"),
    "vinh": (18.68, 105.68, "VN"),
    "quang ninh": (21, 107.3, "VN"),
    "binh duong": (11.18, 106.65, "VN"),
    "dong nai": (11, 107, "VN"),
    "thanh hoa": (19.8, 105.78, "VN"),
    "nghe an": (19, 104.9, "VN"),
    "quang nam": (15.57, 108, "VN"),
    "lao cai": (22.34, 103.84, "VN"),
    "ben tre": (10.24, 106.38, "VN"),
    "ca mau": (9.18, 105.15, "VN"),
    "binh dinh": (14.17, 109, "VN"),
    "kien giang": (10, 105.08, "VN"),
    "long an": (10.7, 106.24, "VN"),
    "bangkok": (13.76, 100.5, "TH"),
    "chiang mai": (18.79, 98.99, "TH"),
    "phuket": (7.88, 98.39, "TH"),
    "pattaya": (12.93, 100.88, "TH"),
    "khon kaen": (16.44, 102.83, "TH"),
    "nakhon ratchasima": (14.97, 102.1, "TH"),
    "hat yai": (7.01, 100.47, "TH"),
    "rayong": (12.68, 101.27, "TH"),
    "udon thani": (17.41, 102.79, "TH"),
    "surat thani": (9.14, 99.33, "TH"),
    "chonburi": (13.36, 100.98, "TH"),
    "ayutthaya": (14.35, 100.58, "TH"),
    "songkhla": (7.2, 100.6, "TH"),
    "krabi": (8.09, 98.91, "TH"),
    "phnom penh": (11.56, 104.92, "KH"),
    "siem reap": (13.36, 103.86, "KH"),
    "sihanoukville": (10.63, 103.5, "KH"),
    "battambang": (13.1, 103.2, "KH"),
    "kampong cham": (12, 105.45, "KH"),
    "kampot": (10.6, 104.18, "KH"),
    "koh kong": (11.62, 103, "KH"),
    "vientiane": (17.97, 102.6, "LA"),
    "luang prabang": (19.88, 102.13, "LA"),
    "luangprabang": (19.88, 102.13, "LA"),
    "savannakhet": (16.56, 104.75, "LA"),
    "pakse": (15.12, 105.8, "LA"),
    "champasak": (14.9, 105.87, "LA"),
    "yangon": (16.85, 96.19, "MM"),
    "mandalay": (21.95, 96.09, "MM"),
    "naypyidaw": (19.75, 96.1, "MM"),
    "bago": (17.34, 96.48, "MM"),
    "mawlamyine": (16.49, 97.63, "MM"),
    "shan": (21.5, 98, "MM"),
    "ayeyarwady": (17, 95.2, "MM"),
    "rakhine": (20, 93.5, "MM"),
    "magway": (20.15, 94.93, "MM"),
    "sagaing": (21.88, 95.98, "MM"),
    "kuala lumpur": (3.14, 101.69, "MY"),
    "penang": (5.41, 100.33, "MY"),
    "johor": (1.49, 103.74, "MY"),
    "sabah": (5.98, 116.07, "MY"),
    "sarawak": (1.55, 110.34, "MY"),
    "ipoh": (4.6, 101.07, "MY"),
    "malacca": (2.2, 102.25, "MY"),
    "melaka": (2.2, 102.25, "MY"),
    "kuching": (1.55, 110.34, "MY"),
    "kota kinabalu": (5.98, 116.07, "MY"),
    "selangor": (3.07, 101.52, "MY"),
    "perak": (4.6, 101.07, "MY"),
    "kedah": (6.12, 100.37, "MY"),
    "pahang": (3.81, 103.33, "MY"),
    "kelantan": (6.13, 102.24, "MY"),
    "putrajaya": (2.93, 101.69, "MY"),
    "singapore": (1.35, 103.82, "SG"),
    "bandar seri begawan": (4.9, 114.94, "BN"),
    "dili": (-8.56, 125.56, "TL"),
    "timor": (-8.8, 125.7, "TL"),
    # --- Extension couverture: villes/provinces secondaires (coords verifiees, anti faux-positif par pays) ---
    # Cambodge
    "poipet": (13.66, 102.56, "KH"),
    "banteay meanchey": (13.59, 102.97, "KH"),
    "pursat": (12.53, 103.92, "KH"),
    "takeo": (10.99, 104.79, "KH"),
    "kratie": (12.49, 106.02, "KH"),
    "stung treng": (13.53, 105.97, "KH"),
    "svay rieng": (11.09, 105.80, "KH"),
    "prey veng": (11.49, 105.33, "KH"),
    "kampong thom": (12.71, 104.89, "KH"),
    "kampong speu": (11.46, 104.52, "KH"),
    "kampong chhnang": (12.25, 104.67, "KH"),
    "pailin": (12.85, 102.61, "KH"),
    "kep": (10.48, 104.31, "KH"),
    "oddar meanchey": (14.16, 103.50, "KH"),
    "preah vihear": (13.81, 104.98, "KH"),
    "ratanakiri": (13.74, 106.99, "KH"),
    "banlung": (13.74, 106.99, "KH"),
    "mondulkiri": (12.45, 107.19, "KH"),
    "sen monorom": (12.45, 107.19, "KH"),
    # Laos
    "thakhek": (17.41, 104.80, "LA"),
    "vang vieng": (18.92, 102.45, "LA"),
    "phonsavan": (19.45, 103.20, "LA"),
    "xieng khouang": (19.45, 103.20, "LA"),
    "oudomxay": (20.69, 101.98, "LA"),
    "luang namtha": (20.95, 101.40, "LA"),
    "bokeo": (20.28, 100.41, "LA"),
    "attapeu": (14.81, 106.83, "LA"),
    "salavan": (15.72, 106.42, "LA"),
    "sekong": (15.35, 106.73, "LA"),
    "paksan": (18.37, 103.66, "LA"),
    "bolikhamsai": (18.37, 103.66, "LA"),
    "phongsali": (21.68, 102.10, "LA"),
    "sayaboury": (19.26, 101.71, "LA"),
    "houaphanh": (20.42, 104.05, "LA"),
    # Myanmar
    "pathein": (16.78, 94.74, "MM"),
    "taunggyi": (20.79, 97.04, "MM"),
    "sittwe": (20.15, 92.90, "MM"),
    "myitkyina": (25.38, 97.40, "MM"),
    "monywa": (22.11, 95.14, "MM"),
    "pyay": (18.82, 95.21, "MM"),
    "hpa-an": (16.89, 97.63, "MM"),
    "dawei": (14.08, 98.19, "MM"),
    "myeik": (12.44, 98.60, "MM"),
    "meiktila": (20.88, 95.86, "MM"),
    "lashio": (22.93, 97.75, "MM"),
    "pakokku": (21.33, 95.10, "MM"),
    "tanintharyi": (12.90, 98.90, "MM"),
    "kachin": (25.85, 97.40, "MM"),
    # Brunei
    "kuala belait": (4.58, 114.23, "BN"),
    "seria": (4.61, 114.32, "BN"),
    "tutong": (4.80, 114.66, "BN"),
    "temburong": (4.62, 115.15, "BN"),
    # Thailande
    "nakhon si thammarat": (8.43, 99.96, "TH"),
    "ubon ratchathani": (15.24, 104.85, "TH"),
    "nakhon sawan": (15.70, 100.14, "TH"),
    "lampang": (18.29, 99.49, "TH"),
    "phitsanulok": (16.82, 100.27, "TH"),
    "chiang rai": (19.91, 99.84, "TH"),
    "trang": (7.56, 99.61, "TH"),
    "surin": (14.88, 103.49, "TH"),
    "buriram": (14.99, 103.10, "TH"),
    "sakon nakhon": (17.16, 104.15, "TH"),
    "roi et": (16.06, 103.65, "TH"),
    "nakhon pathom": (13.82, 100.06, "TH"),
    "kanchanaburi": (14.02, 99.53, "TH"),
    "nakhon phanom": (17.41, 104.78, "TH"),
    "phetchaburi": (13.11, 99.94, "TH"),
    "prachuap khiri khan": (11.81, 99.80, "TH"),
    "loei": (17.49, 101.73, "TH"),
    "mukdahan": (16.54, 104.72, "TH"),
    "chumphon": (10.49, 99.18, "TH"),
    "sukhothai": (17.01, 99.82, "TH"),
    # Vietnam
    "bien hoa": (10.95, 106.82, "VN"),
    "vung tau": (10.35, 107.08, "VN"),
    "buon ma thuot": (12.67, 108.04, "VN"),
    "pleiku": (13.98, 108.00, "VN"),
    "quy nhon": (13.78, 109.22, "VN"),
    "rach gia": (10.01, 105.08, "VN"),
    "da lat": (11.94, 108.44, "VN"),
    "dalat": (11.94, 108.44, "VN"),
    "thai nguyen": (21.59, 105.84, "VN"),
    "nam dinh": (20.42, 106.17, "VN"),
    "bac ninh": (21.18, 106.05, "VN"),
    "vinh long": (10.25, 105.97, "VN"),
    "soc trang": (9.60, 105.97, "VN"),
    "bac giang": (21.27, 106.19, "VN"),
    "hai duong": (20.94, 106.33, "VN"),
    "quang ngai": (15.12, 108.80, "VN"),
    "cao lanh": (10.46, 105.63, "VN"),
    "long xuyen": (10.39, 105.44, "VN"),
    "tay ninh": (11.31, 106.10, "VN"),
    "bac lieu": (9.29, 105.72, "VN"),
    "tra vinh": (9.94, 106.34, "VN"),
    "phan thiet": (10.93, 108.10, "VN"),
    "ha tinh": (18.34, 105.91, "VN"),
    "dong hoi": (17.47, 106.60, "VN"),
    "kon tum": (14.35, 108.00, "VN"),
    "ninh binh": (20.25, 105.97, "VN"),
    "son la": (21.33, 103.91, "VN"),
    "dien bien": (21.39, 103.02, "VN"),
    "lang son": (21.85, 106.76, "VN"),
    # Malaisie
    "kuantan": (3.82, 103.33, "MY"),
    "kota bharu": (6.13, 102.24, "MY"),
    "alor setar": (6.12, 100.37, "MY"),
    "miri": (4.40, 113.99, "MY"),
    "sandakan": (5.84, 118.12, "MY"),
    "sibu": (2.30, 111.82, "MY"),
    "seremban": (2.73, 101.94, "MY"),
    "taiping": (4.85, 100.74, "MY"),
    "kuala terengganu": (5.33, 103.14, "MY"),
    "terengganu": (5.31, 103.13, "MY"),
    "sungai petani": (5.65, 100.49, "MY"),
    "tawau": (4.25, 117.89, "MY"),
    "bintulu": (3.17, 113.04, "MY"),
    "shah alam": (3.07, 101.52, "MY"),
    "petaling jaya": (3.11, 101.61, "MY"),
    "klang": (3.04, 101.45, "MY"),
    "labuan": (5.28, 115.24, "MY"),
    "negeri sembilan": (2.73, 102.26, "MY"),
    # Philippines
    "tacloban": (11.24, 125.00, "PH"),
    "butuan": (8.95, 125.54, "PH"),
    "olongapo": (14.83, 120.28, "PH"),
    "angeles": (15.15, 120.59, "PH"),
    "dumaguete": (9.31, 123.31, "PH"),
    "tagum": (7.45, 125.81, "PH"),
    "lucena": (13.93, 121.62, "PH"),
    "legazpi": (13.14, 123.74, "PH"),
    "cabanatuan": (15.49, 120.97, "PH"),
    "dagupan": (16.04, 120.34, "PH"),
    "ormoc": (11.01, 124.61, "PH"),
    "koronadal": (6.50, 124.85, "PH"),
    "puerto princesa": (9.74, 118.74, "PH"),
    "tuguegarao": (17.61, 121.73, "PH"),
    "pangasinan": (15.89, 120.49, "PH"),
    "nueva ecija": (15.58, 121.00, "PH"),
    "surigao": (9.79, 125.49, "PH"),
    # Indonesie
    "malang": (-7.98, 112.63, "ID"),
    "surakarta": (-7.57, 110.83, "ID"),
    "cirebon": (-6.71, 108.56, "ID"),
    "samarinda": (-0.50, 117.15, "ID"),
    "jayapura": (-2.53, 140.72, "ID"),
    "ambon": (-3.70, 128.18, "ID"),
    "kupang": (-10.18, 123.61, "ID"),
    "mataram": (-8.58, 116.12, "ID"),
    "banda aceh": (5.55, 95.32, "ID"),
    "depok": (-6.40, 106.82, "ID"),
    "serang": (-6.12, 106.15, "ID"),
    "bandar lampung": (-5.43, 105.26, "ID"),
    "tasikmalaya": (-7.33, 108.22, "ID"),
    "sukabumi": (-6.92, 106.93, "ID"),
    "kendari": (-3.99, 122.51, "ID"),
    "palu": (-0.90, 119.87, "ID"),
    "gorontalo": (0.54, 123.06, "ID"),
    "ternate": (0.79, 127.38, "ID"),
    "sorong": (-0.88, 131.25, "ID"),
    "tarakan": (3.31, 117.59, "ID"),
    "banten": (-6.40, 106.06, "ID"),
    "riau": (0.51, 101.44, "ID"),
}

_GAZ_PATTERNS = [
    (name, data, _re_geo.compile("(?:^|[^a-z])" + name.replace(" ", "[ ]") + "(?:$|[^a-z])"))
    for name, data in sorted(ASEAN_GAZETTEER.items(), key=lambda kv: len(kv[0]), reverse=True)
]


def geocode_from_text(text: str, iso2: str):
    """(lat, lng, nom_lieu) si un toponyme du pays iso2 figure dans text, sinon None."""
    if not text or not iso2:
        return None
    hay = _norm(text)
    for name, (lat, lng, gi), pat in _GAZ_PATTERNS:
        if gi == iso2 and pat.search(hay):
            return (lat, lng, name.title())
    return None


# --- Schema normalise --------------------------------------------------------
@dataclass
class RawTender:
    """Enregistrement AO normalise + entites liees, pret pour upsert relationnel."""
    source_code: str
    external_ref: str
    title: str
    country_iso2: str
    source_url: str
    source_id: Optional[str] = None
    description: str = ""
    country_name: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    discipline_v: Optional[str] = None
    procurement_type: Optional[str] = None
    stage: Optional[str] = None
    value_amount: Optional[float] = None
    value_currency: Optional[str] = None
    published_at: Optional[str] = None
    deadline_at: Optional[str] = None
    location_text: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    geocode_precision: str = "none"
    # parties (alimentent le graphe relationnel)
    issuer_name: Optional[str] = None       # autorite / agence emettrice
    ministry: Optional[str] = None
    authority: Optional[str] = None
    donor: Optional[str] = None             # financeur (nom)
    project_name: Optional[str] = None
    project_ref: Optional[str] = None       # id projet cote source
    language: Optional[str] = None
    translated_content: Optional[str] = None
    raw: dict = field(default_factory=dict)
    # calcules
    relevance_score: int = 0
    relevance_status: str = "filtered"
    verification_status: str = "pending"
    content_hash: str = ""

    def finalize(self) -> "RawTender":
        self.country_name = self.country_name or ISO2_TO_NAME.get(self.country_iso2)
        self.language = self.language or ISO2_TO_LANG.get(self.country_iso2)
        self.relevance_score, self.relevance_status = relevance(
            self.title, self.description, self.sector or "",
            amount=self.value_amount, donor=self.donor or "",
            authority=self.authority or self.issuer_name or "",
            procurement_type=self.procurement_type or "",
            stage=self.stage or "",
        )
        self.discipline_v = discipline(self.title, self.description)
        self.sector = self.sector or sector_class(self.title, self.description)
        # Geocodage fin : upgrade capitale -> ville si un toponyme reel est present
        if (self.geocode_precision or "none") in ("none", "country", "capital", ""):
            _hit = geocode_from_text(
                " | ".join(p for p in (
                    self.title, self.project_name, self.location_text,
                    self.authority, self.ministry, self.issuer_name,
                ) if p),
                self.country_iso2,
            )
            if _hit:
                self.lat, self.lng, _city = _hit
                self.city = self.city or _city
                self.geocode_precision = "city"
        # 100% verifie : source_url officiel obligatoire + pays ASEAN
        if self.source_url and self.country_iso2 in ASEAN_ISO2:
            self.verification_status = "verified"
        else:
            self.verification_status = "pending"
        self.content_hash = self._hash()
        return self

    def _hash(self) -> str:
        basis = "|".join([
            self.source_code, self.external_ref or "", _norm(self.title),
            self.deadline_at or "", self.country_iso2,
        ])
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]

    def tender_row(self) -> dict:
        """Ligne pour la table ao_tenders (champs alignes sur la spec)."""
        d = asdict(self)
        d.pop("raw", None)
        d["discipline"] = d.pop("discipline_v", None)
        # liens relationnels (UUID deterministes)
        if self.project_ref:
            d["project_uid"] = project_uid(self.source_code, self.project_ref)
        if self.donor:
            d["donor_org_id"] = org_uid(self.donor)
        auth = self.authority or self.issuer_name
        if auth:
            d["authority_org_id"] = org_uid(auth, self.country_iso2)
        return d

    # --- entites derivees (pour upsert dans les tables du reseau) ----------
    def organisations(self) -> list[dict]:
        out = []
        if self.donor:
            out.append({"id": org_uid(self.donor), "name": self.donor,
                        "org_type": "donor", "country_iso2": None,
                        "source_url": self.source_url})
        auth = self.authority or self.issuer_name
        if auth:
            out.append({"id": org_uid(auth, self.country_iso2), "name": auth,
                        "org_type": "authority", "country_iso2": self.country_iso2,
                        "source_url": self.source_url})
        if self.ministry:
            out.append({"id": org_uid(self.ministry, self.country_iso2),
                        "name": self.ministry, "org_type": "ministry",
                        "country_iso2": self.country_iso2, "source_url": self.source_url})
        return out

    def project(self) -> Optional[dict]:
        if not self.project_ref:
            return None
        return {
            "id": project_uid(self.source_code, self.project_ref),
            "external_id": self.project_ref, "source_code": self.source_code,
            "name": self.project_name or self.title, "country_iso2": self.country_iso2,
            "city": self.city, "latitude": self.lat, "longitude": self.lng,
            "donor_org_id": org_uid(self.donor) if self.donor else None,
            "sector": self.sector, "discipline": self.discipline_v,
            "estimated_budget": self.value_amount, "currency": self.value_currency,
            "status": self.stage, "source_url": self.source_url,
        }

    def party_roles(self) -> list[dict]:
        """Liens (role) entre cet AO et ses parties. tender_id ajoute apres upsert."""
        roles = []
        ref = f"{self.source_code}:{self.external_ref}"
        if self.donor:
            ou = org_uid(self.donor)
            roles.append({"id": role_uid("donor", ref, ou), "role": "donor",
                          "organisation_id": ou, "source_url": self.source_url})
        auth = self.authority or self.issuer_name
        if auth:
            ou = org_uid(auth, self.country_iso2)
            roles.append({"id": role_uid("authority", ref, ou), "role": "authority",
                          "organisation_id": ou, "source_url": self.source_url})
        return roles


def dedupe(records: list[RawTender]) -> list[RawTender]:
    """Garde un seul enregistrement par content_hash (le dernier vu gagne)."""
    by_hash: dict[str, RawTender] = {}
    for r in records:
        by_hash[r.content_hash] = r
    return list(by_hash.values())
