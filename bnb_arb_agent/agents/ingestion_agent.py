"""Data ingestion agent — collects crypto news from multiple sources."""

import abc
from datetime import datetime
from typing import Any

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup
from gnews import GNews
from pytrends.request import TrendReq

from config import Config
from core.logger import get_logger

logger = get_logger(__name__)
config = Config()

Article = dict[str, Any]

_DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BNBArbBot/1.0)"}


class BaseIngester(abc.ABC):
    """Interface that every data source ingester must implement."""

    @abc.abstractmethod
    def fetch(self, **kwargs) -> list[Article]:
        """Fetch articles and return a list of normalised article dicts."""


class GNewsIngester(BaseIngester):
    def __init__(self) -> None:
        self._client = GNews(language="en", country="US", period="1d", max_results=15)

    def fetch(self, query: str = "BNB") -> list[Article]:
        try:
            articles = self._client.get_news(query)
            return [
                {
                    "source":    f"GNews/{a.get('publisher', {}).get('title', 'Unknown')}",
                    "title":     a.get("title", ""),
                    "content":   a.get("description", ""),
                    "url":       a.get("url", ""),
                    "timestamp": a.get("published date", ""),
                }
                for a in articles
            ]
        except Exception:
            logger.exception("GNews fetch failed for query '%s'.", query)
            return []


class RSSIngester(BaseIngester):
    _FEEDS = {
        "CoinDesk":       "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "CoinTelegraph":  "https://cointelegraph.com/rss",
        "Decrypt":        "https://decrypt.co/feed",
        "CryptoNews":     "https://cryptonews.com/news/feed/",
        "BeInCrypto":     "https://beincrypto.com/feed/",
        "TheBlock":       "https://www.theblock.co/rss.xml",
        "BitcoinMagazine":"https://bitcoinmagazine.com/.rss/full/",
        "NewsbtcFeed":    "https://www.newsbtc.com/feed/",
        "AMBCrypto":      "https://ambcrypto.com/feed/",
        "U.Today":        "https://u.today/rss",
    }

    def fetch(self, keywords: list[str] = None) -> list[Article]:
        keywords = keywords or []
        results  = []
        for name, url in self._FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    if not keywords or any(k.lower() in title.lower() for k in keywords):
                        results.append({
                            "source":    f"RSS/{name}",
                            "title":     title,
                            "content":   entry.get("summary", "")[:400],
                            "url":       entry.get("link", ""),
                            "timestamp": entry.get("published", ""),
                        })
            except Exception:
                logger.warning("RSS feed failed: %s", name)
        return results


class CryptoPanicIngester(BaseIngester):
    _BASE_URL = "https://cryptopanic.com/api/developer/v2/posts/"

    def fetch(self, currencies: str = "BNB,CAKE") -> list[Article]:
        if not config.cryptopanic_key:
            return []
        try:
            response = requests.get(
                self._BASE_URL,
                params={
                    "auth_token": config.cryptopanic_key,
                    "currencies": currencies,
                    "filter":     "hot",
                    "public":     "true",
                },
                timeout=10,
            )
            response.raise_for_status()
            return [
                {
                    "source":    f"CryptoPanic/{p.get('source', {}).get('title', 'CP')}",
                    "title":     p.get("title", ""),
                    "content":   "",
                    "url":       p.get("url", ""),
                    "timestamp": p.get("published_at", ""),
                }
                for p in response.json().get("results", [])
            ]
        except requests.HTTPError as exc:
            logger.warning("CryptoPanic request failed: %s", exc)
            return []
        except Exception:
            logger.exception("CryptoPanic ingestion error.")
            return []


class GoogleTrendsIngester(BaseIngester):
    def __init__(self) -> None:
        self._client = None

    def _connect(self) -> bool:
        if self._client is not None:
            return True
        try:
            self._client = TrendReq(hl="en-US", tz=360, timeout=(5, 10))
            return True
        except Exception:
            logger.warning("Google Trends client could not initialise.")
            return False

    def fetch(self, keywords: list[str] = None) -> list[Article]:
        keywords = keywords or []
        if not keywords or not self._connect():
            return []
        try:
            self._client.build_payload(keywords[:5], cat=0, timeframe="now 1-d", geo="")
            interest = self._client.interest_over_time()
            if interest.empty:
                return []
            latest = interest.iloc[-1]
            return [
                {
                    "source":    "GoogleTrends",
                    "title":     f"Trend score for '{kw}': {latest[kw]}",
                    "content":   f"Google search trend score: {latest[kw]}/100",
                    "url":       "",
                    "timestamp": str(interest.index[-1]),
                }
                for kw in keywords[:5]
                if kw in latest
            ]
        except Exception:
            logger.exception("Google Trends fetch failed.")
            return []


class WebScraper(BaseIngester):
    def fetch(self, keyword: str = "BNB") -> list[Article]:
        return self._scrape_bitcointalk(keyword) + self._scrape_4chan(keyword)

    def _scrape_bitcointalk(self, keyword: str) -> list[Article]:
        try:
            url  = f"https://bitcointalk.org/index.php?action=search2&search={keyword}&sort_order=DESC"
            soup = BeautifulSoup(requests.get(url, headers=_DEFAULT_HEADERS, timeout=10).text, "html.parser")
            return [
                {
                    "source":    "Bitcointalk",
                    "title":     link.text.strip(),
                    "content":   "",
                    "url":       link.get("href", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                for row in soup.select("td.windowbg")[:10]
                if (link := row.find("a"))
            ]
        except Exception:
            logger.warning("Bitcointalk scrape failed.")
            return []

    def _scrape_4chan(self, keyword: str) -> list[Article]:
        try:
            data = requests.get("https://a.4cdn.org/biz/catalog.json", timeout=10).json()
            results = []
            for page in data:
                for thread in page.get("threads", []):
                    text = (thread.get("sub") or "") + (thread.get("com") or "")
                    if keyword.lower() not in text.lower():
                        continue
                    results.append({
                        "source":    "4chan/biz",
                        "title":     (thread.get("sub") or thread.get("com") or "")[:100],
                        "content":   (thread.get("com") or "")[:400],
                        "url":       f"https://boards.4channel.org/biz/thread/{thread['no']}",
                        "timestamp": datetime.utcfromtimestamp(thread.get("time", 0)).isoformat(),
                    })
            return results
        except Exception:
            logger.warning("4chan scrape failed.")
            return []


class CoinGeckoTrendIngester(BaseIngester):
    def fetch(self) -> list[Article]:
        try:
            data = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=8).json()
            return [
                {
                    "source":    "CoinGecko/Trending",
                    "title":     f"{c['name']} ({c['symbol']}) trending #{c['market_cap_rank']}",
                    "content":   f"Price BTC: {c.get('price_btc', 0):.8f}",
                    "url":       f"https://coingecko.com/en/coins/{c['id']}",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                for item in data.get("coins", [])
                if (c := item["item"])
            ]
        except Exception:
            logger.warning("CoinGecko trending fetch failed.")
            return []


class DataIngestionAgent:
    """Orchestrates all ingesters and returns a deduplicated DataFrame."""

    def __init__(self) -> None:
        self._gnews      = GNewsIngester()
        self._rss        = RSSIngester()
        self._cryptopanic = CryptoPanicIngester()
        self._trends     = GoogleTrendsIngester()
        self._scraper    = WebScraper()
        self._coingecko  = CoinGeckoTrendIngester()

    def run(self, tokens: list[str] = None, keywords: list[str] = None) -> pd.DataFrame:
        tokens   = tokens   or config.target_tokens
        keywords = keywords or config.search_keywords
        articles: list[Article] = []

        logger.info("Fetching from all sources.")

        for keyword in keywords[:3]:
            articles += self._gnews.fetch(query=keyword)

        articles += self._rss.fetch(keywords=keywords)
        articles += self._cryptopanic.fetch(currencies=",".join(tokens))
        articles += self._trends.fetch(keywords=tokens[:5])
        articles += self._coingecko.fetch()

        for token in tokens[:2]:
            articles += self._scraper.fetch(keyword=token)

        dataframe = pd.DataFrame(articles).drop_duplicates(subset=["title"])
        dataframe["fetched_at"] = datetime.utcnow().isoformat()

        logger.info("Collected %d items from %d sources.", len(dataframe), dataframe["source"].nunique())
        return dataframe