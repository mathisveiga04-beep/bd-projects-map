import logging
import requests
from .common import Opportunity


# Pays ASEAN couverts par le scraper Banque mondiale.
# Memes consignes/contraintes que le Cambodge ; (code ISO2, nom pays).
ASEAN_COUNTRIES = [
    ("KH", "Cambodia"),
    ("VN", "Vietnam"),
    ("TH", "Thailand"),
    ("LA", "Laos"),
    ("MM", "Myanmar"),
    ("ID", "Indonesia"),
    ("PH", "Philippines"),
    ("MY", "Malaysia"),
    ("SG", "Singapore"),
    ("BN", "Brunei Darussalam"),
]


def _scrape_country(iso2: str, country_name: str, limit: int = 5):
    url = "https://search.worldbank.org/api/v2/projects"
    params = {"format": "json", "countrycode_exact": iso2, "rows": limit}
    items = []
    try:
        data = requests.get(url, params=params, timeout=20).json()
        projects = data.get("projects", {}) if isinstance(data, dict) else {}
        for _, p in list(projects.items())[:limit]:
            title = p.get("project_name") or p.get("project_abstract") or "World Bank project"
            text = "\n".join(str(p.get(k, "")) for k in ["project_abstract", "projectdocs", "theme_namecode", "sector_namecode"])
            source_url = p.get("url") or "https://projects.worldbank.org/"
            items.append(Opportunity(title=title, text=text, source="World Bank", source_url=source_url, funder="World Bank", country=country_name))
    except Exception as exc:
        logging.getLogger(__name__).warning("World Bank scraper failed for %s: %s", iso2, exc)
    return items


def scrape_world_bank_cambodia(limit: int = 25):
    # Nom historique conserve pour compat. Couvre desormais tout l'ASEAN.
    # Round-robin entre pays pour qu'un plafond global capte un mix multi-pays.
    per_country = max(2, min(8, limit // 2))
    buckets = [_scrape_country(iso2, name, per_country) for iso2, name in ASEAN_COUNTRIES]
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
