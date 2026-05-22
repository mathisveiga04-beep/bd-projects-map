import requests
from .common import Opportunity


def scrape_world_bank_cambodia(limit: int = 25):
    # World Bank Projects API; endpoint may evolve, so this stays defensive.
    url = "https://search.worldbank.org/api/v2/projects"
    params = {"format": "json", "countrycode_exact": "KH", "rows": limit}
    items = []
    try:
        data = requests.get(url, params=params, timeout=20).json()
        projects = data.get("projects", {}) if isinstance(data, dict) else {}
        for _, p in list(projects.items())[:limit]:
            title = p.get("project_name") or p.get("project_abstract") or "World Bank project"
            text = "\n".join(str(p.get(k, "")) for k in ["project_abstract", "projectdocs", "theme_namecode", "sector_namecode"])
            source_url = p.get("url") or "https://projects.worldbank.org/"
            items.append(Opportunity(title=title, text=text, source="World Bank", source_url=source_url, funder="World Bank"))
    except Exception as exc:
        items.append(Opportunity(title="World Bank scraper error", text=str(exc), source="World Bank", source_url=url))
    return items
