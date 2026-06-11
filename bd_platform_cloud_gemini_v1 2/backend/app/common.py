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
              authority: str = "", procurement_type: str = "") -> tuple[int, str]:
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

    score = min(score, 100)
    status = "kept" if score >= 8 else "filtered"
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
        )
        self.discipline_v = discipline(self.title, self.description)
        self.sector = self.sector or sector_class(self.title, self.description)
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
