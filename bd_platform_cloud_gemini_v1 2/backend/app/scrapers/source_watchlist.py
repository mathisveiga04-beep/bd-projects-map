from .common import Opportunity
from ..sources import active_sources


# Pays ASEAN couverts par la watchlist des sources.
# Memes consignes / contraintes que le Cambodge, appliquees a tout l'ASEAN.
ASEAN_COUNTRIES = [
    "Cambodia",
    "Vietnam",
    "Thailand",
    "Laos",
    "Myanmar",
    "Indonesia",
    "Philippines",
    "Malaysia",
    "Singapore",
    "Brunei Darussalam",
    "Timor-Leste",
]


def scrape_default_source_watchlist(limit: int = 100):
    items = []
    sources = active_sources()
    # Round-robin pays x sources: on alterne les pays pour qu'un plafond
    # global capte un mix multi-pays (meme logique que le Cambodge partout).
    buckets = [[(country, source) for source in sources] for country in ASEAN_COUNTRIES]
    combos = []
    idx = 0
    while any(idx < len(b) for b in buckets):
        for b in buckets:
            if idx < len(b):
                combos.append(b[idx])
        idx += 1
    for country, source in combos[:limit]:
        keywords = ", ".join(source["keywords"])
        text = (
            f"Default active {country} opportunity source for Artelia BD monitoring.\n"
            f"Source: {source['name']}\n"
            f"URL: {source['url']}\n"
            f"Country: {country}\n"
            f"Keywords tracked by Gemini: {keywords}\n"
            "Use this source to detect procurement notices, donor-funded projects, "
            "engineering consultancy missions, supervision assignments, PMO/PMC roles, "
            "water, drainage, transport, power grid, renewable energy and climate resilience opportunities."
        )
        items.append(
            Opportunity(
                title=f"{source['name']} {country} opportunity watch",
                text=text,
                source=source["name"],
                source_url=source["url"],
                funder=source["name"],
                country=country,
            )
        )
    return items
