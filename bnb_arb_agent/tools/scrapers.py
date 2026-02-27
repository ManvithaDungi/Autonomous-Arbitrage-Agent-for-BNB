import asyncio
from typing import List, Dict, Any


def _format_gnews_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "published": item.get("published date") or item.get("published"),
        "source": item.get("publisher") or item.get("source"),
        "description": item.get("description"),
    }


def _fetch_gnews(query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        from gnews import GNews
        g = GNews(language="en", max_results=limit)
        items = g.get_news(query)
        return [_format_gnews_item(i) for i in items]
    except Exception:
        return []


def _fetch_feedparser(query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        import feedparser
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={query}")
        out = []
        for e in feed.entries[:limit]:
            out.append(
                {
                    "title": getattr(e, "title", None),
                    "url": getattr(e, "link", None),
                    "published": getattr(e, "published", None),
                    "source": "GoogleNewsRSS",
                    "description": getattr(e, "summary", None),
                }
            )
        return out
    except Exception:
        return []


async def fetch_recent_news(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    def load():
        primary = _fetch_gnews(query, limit)
        if primary:
            return primary
        return _fetch_feedparser(query, limit)

    return await asyncio.to_thread(load)
