# agents/ingestion_agent.py

import requests
import feedparser
from bs4 import BeautifulSoup
from gnews import GNews
from pytrends.request import TrendReq
from datetime import datetime
import pandas as pd
from config import Config

cfg = Config()

# ─────────────────────────────────────────
# 1. GNEWS (Google News aggregator)
# ─────────────────────────────────────────
class GNewsIngester:
    def __init__(self):
        self.gn = GNews(language='en', country='US', period='1d', max_results=15)

    def fetch(self, query):
        results = []
        try:
            articles = self.gn.get_news(query)
            for a in articles:
                results.append({
                    "source": f"GNews/{a.get('publisher', {}).get('title', 'Unknown')}",
                    "title": a.get("title", ""),
                    "content": a.get("description", ""),
                    "url": a.get("url", ""),
                    "timestamp": a.get("published date", ""),
                    "engagement": 0
                })
        except Exception as e:
            print(f"[GNews Error] {e}")
        return results


# ─────────────────────────────────────────
# 4. RSS FEEDS (CoinDesk, CoinTelegraph, Decrypt, etc.)
# ─────────────────────────────────────────
class RSSIngester:
    FEEDS = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "CoinTelegraph": "https://cointelegraph.com/rss",
        "Decrypt": "https://decrypt.co/feed",
        "CryptoNews": "https://cryptonews.com/news/feed/",
        "BeInCrypto": "https://beincrypto.com/feed/",
        "TheBlock": "https://www.theblock.co/rss.xml",
        "BitcoinMagazine": "https://bitcoinmagazine.com/.rss/full/",
        "NewsbtcFeed": "https://www.newsbtc.com/feed/",
        "AMBCrypto": "https://ambcrypto.com/feed/",
        "U.Today": "https://u.today/rss"
    }

    def fetch(self, keywords):
        results = []
        for name, url in self.FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    # Filter by keyword relevance
                    if any(k.lower() in title.lower() for k in keywords):
                        results.append({
                            "source": f"RSS/{name}",
                            "title": title,
                            "content": entry.get("summary", "")[:400],
                            "url": entry.get("link", ""),
                            "timestamp": entry.get("published", ""),
                            "engagement": 0
                        })
            except Exception as e:
                print(f"[RSS/{name} Error] {e}")
        return results


# ─────────────────────────────────────────
# 5. CRYPTOPANIC (Crypto-specific news aggregator)
# ─────────────────────────────────────────
class CryptoPanicIngester:
    BASE_URL = "https://cryptopanic.com/api/v1/posts/"

    def fetch(self, currencies="BNB,CAKE"):
        results = []
        try:
            params = {
                "auth_token": cfg.CRYPTOPANIC_KEY,
                "currencies": currencies,
                "filter": "hot",
                "public": "true"
            }
            data = requests.get(self.BASE_URL, params=params).json()
            for post in data.get("results", []):
                results.append({
                    "source": f"CryptoPanic/{post.get('source', {}).get('title', 'CP')}",
                    "title": post.get("title", ""),
                    "content": "",
                    "url": post.get("url", ""),
                    "timestamp": post.get("published_at", ""),
                    "engagement": post.get("votes", {}).get("positive", 0)
                })
        except Exception as e:
            print(f"[CryptoPanic Error] {e}")
        return results





# ─────────────────────────────────────────
# 7. GOOGLE TRENDS via PyTrends
# ─────────────────────────────────────────
class GoogleTrendsIngester:
    def __init__(self):
        self.pytrends = TrendReq(hl='en-US', tz=360)

    def fetch(self, keywords):
        results = []
        try:
            self.pytrends.build_payload(keywords[:5], cat=0, timeframe='now 1-d', geo='')
            interest = self.pytrends.interest_over_time()
            if not interest.empty:
                latest = interest.iloc[-1]
                for kw in keywords[:5]:
                    if kw in latest:
                        results.append({
                            "source": "GoogleTrends",
                            "title": f"Trend score for '{kw}': {latest[kw]}",
                            "content": f"Google search trend score: {latest[kw]}/100",
                            "url": "",
                            "timestamp": str(interest.index[-1]),
                            "engagement": int(latest[kw])
                        })
        except Exception as e:
            print(f"[GoogleTrends Error] {e}")
        return results


# ─────────────────────────────────────────
# 8. WEB SCRAPER - Bitcointalk, 4chan /biz/, Quora
# ─────────────────────────────────────────
class WebScraper:
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BNBArbBot/1.0)"}

    def scrape_bitcointalk(self, keyword):
        results = []
        try:
            url = f"https://bitcointalk.org/index.php?action=search2&search={keyword}&sort_order=DESC"
            soup = BeautifulSoup(requests.get(url, headers=self.HEADERS, timeout=10).text, "html.parser")
            for row in soup.select("td.windowbg")[:10]:
                link = row.find("a")
                if link:
                    results.append({
                        "source": "Bitcointalk",
                        "title": link.text.strip(),
                        "content": "",
                        "url": link.get("href", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                        "engagement": 0
                    })
        except Exception as e:
            print(f"[Bitcointalk Error] {e}")
        return results

    def scrape_4chan_biz(self, keyword):
        results = []
        try:
            url = "https://a.4cdn.org/biz/catalog.json"
            data = requests.get(url, timeout=10).json()
            for page in data:
                for thread in page.get("threads", []):
                    sub = thread.get("sub", "") or ""
                    com = thread.get("com", "") or ""
                    if keyword.lower() in (sub + com).lower():
                        results.append({
                            "source": "4chan/biz",
                            "title": sub[:100] or com[:100],
                            "content": com[:400],
                            "url": f"https://boards.4channel.org/biz/thread/{thread['no']}",
                            "timestamp": datetime.utcfromtimestamp(thread.get("time", 0)).isoformat(),
                            "engagement": thread.get("replies", 0)
                        })
        except Exception as e:
            print(f"[4chan Error] {e}")
        return results


# ─────────────────────────────────────────
# 9. COINGECKO TRENDING (on-chain data signal)
# ─────────────────────────────────────────
class CoinGeckoTrendIngester:
    def fetch(self):
        results = []
        try:
            data = requests.get("https://api.coingecko.com/api/v3/search/trending").json()
            for item in data.get("coins", []):
                coin = item["item"]
                results.append({
                    "source": "CoinGecko/Trending",
                    "title": f"{coin['name']} ({coin['symbol']}) trending #{coin['market_cap_rank']}",
                    "content": f"Price BTC: {coin.get('price_btc', 0):.8f}",
                    "url": f"https://coingecko.com/en/coins/{coin['id']}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "engagement": coin.get("score", 0)
                })
        except Exception as e:
            print(f"[CoinGecko Error] {e}")
        return results


# ─────────────────────────────────────────
# 🔄 MASTER INGESTION AGENT
# ─────────────────────────────────────────
class DataIngestionAgent:
    def __init__(self):
        self.gnews = GNewsIngester()
        self.rss = RSSIngester()
        self.cryptopanic = CryptoPanicIngester()
        self.trends = GoogleTrendsIngester()
        self.scraper = WebScraper()
        self.coingecko = CoinGeckoTrendIngester()

    def run(self, tokens=None, keywords=None):
        tokens = tokens or cfg.TARGET_TOKENS
        keywords = keywords or cfg.SEARCH_KEYWORDS
        all_data = []

        print("🔄 Fetching from ALL sources...")

        for keyword in keywords[:3]:   # Limit to avoid rate limits in hackathon
            all_data += self.gnews.fetch(keyword)

        all_data += self.rss.fetch(keywords)
        all_data += self.cryptopanic.fetch(",".join(tokens))
        all_data += self.trends.fetch(tokens[:5])
        all_data += self.coingecko.fetch()

        for token in tokens[:2]:
            all_data += self.scraper.scrape_bitcointalk(token)
            all_data += self.scraper.scrape_4chan_biz(token)

        df = pd.DataFrame(all_data).drop_duplicates(subset=["title"])
        df["fetched_at"] = datetime.utcnow().isoformat()
        print(f"✅ Total items collected: {len(df)} from {df['source'].nunique()} sources")
        return df