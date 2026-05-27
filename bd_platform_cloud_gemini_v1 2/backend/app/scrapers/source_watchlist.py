from .common import Opportunity
from ..sources import active_sources


def scrape_default_source_watchlist(limit: int = 100):
    items = []
    for source in active_sources()[:limit]:
        keywords = ", ".join(source["keywords"])
        text = (
            f"Default active Cambodia opportunity source for Artelia BD monitoring.\n"
            f"Source: {source['name']}\n"
            f"URL: {source['url']}\n"
            f"Keywords tracked by Gemini: {keywords}\n"
            "Use this source to detect procurement notices, donor-funded projects, "
            "engineering consultancy missions, supervision assignments, PMO/PMC roles, "
            "water, drainage, transport, power grid, renewable energy and climate resilience opportunities."
        )
        items.append(
            Opportunity(
                title=f"{source['name']} Cambodia opportunity watch",
                text=text,
                source=source["name"],
                source_url=source["url"],
                funder=source["name"],
            )
        )
    return items
