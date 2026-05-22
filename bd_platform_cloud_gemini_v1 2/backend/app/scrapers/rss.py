import os
import feedparser
from .common import Opportunity


def scrape_rss_sources(limit: int = 30):
    urls = [u.strip() for u in os.getenv("RSS_SOURCES", "").split(",") if u.strip()]
    items = []
    for url in urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", url)
            items.append(Opportunity(title=title, text=summary, source="RSS", source_url=link))
    return items
