# agents/prediction_market_agent.py
# predict.fun Integration for BNB Arb Agent
# Uses prediction market odds as forward-looking price signals
#
# How it helps your arb agent:
#   - Prediction odds  = crowd's probability of future price movement
#   - Rising YES price = market expects bullish move → front-run the arb
#   - Falling YES price= market expects bearish move → avoid entering
#   - Orderbook depth  = liquidity signal (thin book = high volatility coming)

import requests
import json
from datetime import datetime
from typing import Optional
from config import Config

cfg = Config()

# ── API endpoints ──
# Testnet: no API key needed (use this for hackathon!)
# Mainnet: requires x-api-key header (get from Discord)
TESTNET_BASE  = "https://api-testnet.predict.fun/v1"
MAINNET_BASE  = "https://api.predict.fun/v1"


class PredictFunClient:
    """
    REST client for predict.fun API.
    Automatically uses testnet if no API key is set.
    """

    def __init__(self, api_key: Optional[str] = None, use_testnet: bool = True):
        self.api_key     = api_key or getattr(cfg, 'PREDICT_FUN_API_KEY', None)
        self.use_testnet = use_testnet or not self.api_key
        self.base_url    = TESTNET_BASE if self.use_testnet else MAINNET_BASE
        self.headers     = {"Content-Type": "application/json"}
        if self.api_key and not self.use_testnet:
            self.headers["x-api-key"] = self.api_key
        network = "TESTNET (no key needed)" if self.use_testnet else "MAINNET"
        print(f"[PredictFun] Connected to {network}: {self.base_url}")

    def _get(self, endpoint: str, params: dict = None) -> dict:
        try:
            url = f"{self.base_url}{endpoint}"
            res = requests.get(url, headers=self.headers, params=params, timeout=8)
            return res.json()
        except Exception as e:
            print(f"[PredictFun API Error] {endpoint}: {e}")
            return {"success": False, "data": []}

    # ── Markets ──
    def get_markets(self, limit: int = 50, category: str = None) -> list:
        """Fetch all active prediction markets."""
        params = {"limit": limit}
        if category:
            params["category"] = category
        data = self._get("/markets", params)
        return data.get("data", []) if data.get("success") else []

    def get_market_by_id(self, market_id: int) -> dict:
        data = self._get(f"/markets/{market_id}")
        return data.get("data", {}) if data.get("success") else {}

    def get_market_stats(self, market_id: int) -> dict:
        data = self._get(f"/markets/{market_id}/statistics")
        return data.get("data", {}) if data.get("success") else {}

    def get_orderbook(self, market_id: int) -> dict:
        """
        Returns bids/asks for YES side.
        Price range: 0.0 to 1.0 (= 0% to 100% probability)
        """
        data = self._get(f"/markets/{market_id}/orderbook")
        return data.get("data", {}) if data.get("success") else {}

    def get_last_sale(self, market_id: int) -> dict:
        data = self._get(f"/markets/{market_id}/last-sale")
        return data.get("data", {}) if data.get("success") else {}

    def search_markets(self, query: str) -> list:
        data = self._get("/search", {"query": query})
        return data.get("data", {}).get("markets", []) if data.get("success") else []


# ═══════════════════════════════════════════════════════════
# 🔮 PREDICTION MARKET SIGNAL ANALYZER
# Converts prediction market data into arb signals
# ═══════════════════════════════════════════════════════════
class PredictionMarketAgent:

    # Keywords to match BNB-related prediction markets
    TOKEN_SEARCH_TERMS = {
        "BNB":      ["BNB", "Binance Coin", "BNB price", "BNB above", "BNB below"],
        "CAKE":     ["CAKE", "PancakeSwap", "CAKE price"],
        "BTC":      ["Bitcoin", "BTC price", "BTC above", "BTC below"],
        "ETH":      ["Ethereum", "ETH price", "ETH above"],
        "BTCB":     ["Bitcoin", "BTC", "BTCB"],
        "BabyDoge": ["BabyDoge", "Baby Doge"],
    }

    def __init__(self, use_testnet: bool = True):
        self.client = PredictFunClient(use_testnet=use_testnet)
        self._market_cache = {}   # cache market list to avoid repeated calls

    def _get_all_markets(self) -> list:
        if not self._market_cache.get("markets"):
            self._market_cache["markets"] = self.client.get_markets(limit=100)
            self._market_cache["fetched_at"] = datetime.utcnow()
        return self._market_cache.get("markets", [])

    def find_token_markets(self, token: str) -> list:
        """Find all prediction markets related to a specific token."""
        all_markets = self._get_all_markets()
        search_terms = self.TOKEN_SEARCH_TERMS.get(token, [token])
        matched = []

        for market in all_markets:
            title       = market.get("title", "").lower()
            description = market.get("description", "").lower()
            combined    = title + " " + description

            if any(term.lower() in combined for term in search_terms):
                matched.append(market)

        # Also try direct search API
        for term in search_terms[:2]:
            search_results = self.client.search_markets(term)
            for r in search_results:
                if r not in matched:
                    matched.append(r)

        return matched

    def analyze_market_signal(self, market: dict) -> dict:
        """
        Analyze a single prediction market for arb signals.

        Key insight:
          - YES price near 1.0 = market very confident price will go UP
          - YES price near 0.0 = market very confident price will go DOWN
          - YES price near 0.5 = uncertain (high volatility expected)
          - Rising YES price   = bullish momentum forming
          - Thin orderbook     = low liquidity = bigger price swings coming
        """
        market_id = market.get("id") or market.get("marketId")
        if not market_id:
            return {}

        orderbook = self.client.get_orderbook(market_id)
        last_sale = self.client.get_last_sale(market_id)
        stats     = self.client.get_market_stats(market_id)

        # ── Current YES probability from best bid/ask ──
        bids = orderbook.get("bids", [])   # [[price, qty], ...]
        asks = orderbook.get("asks", [])

        best_bid    = bids[0][0]  if bids else 0.0
        best_ask    = asks[0][0]  if asks else 0.0
        mid_price   = (best_bid + best_ask) / 2 if (best_bid and best_ask) else best_bid or best_ask
        spread      = round(best_ask - best_bid, 4) if (best_bid and best_ask) else 0

        # ── Last traded price ──
        last_price  = float(last_sale.get("price", mid_price) or mid_price)

        # ── Liquidity depth (sum of top 5 levels) ──
        bid_liquidity = sum(level[1] for level in bids[:5]) if bids else 0
        ask_liquidity = sum(level[1] for level in asks[:5]) if asks else 0
        total_liquidity = bid_liquidity + ask_liquidity

        # ── Volume from stats ──
        volume_24h = float(stats.get("volume24h", 0) or 0)
        volume_total = float(stats.get("volumeTotal", 0) or 0)

        # ── Signal interpretation ──
        if mid_price >= 0.75:
            direction_signal = "STRONG_BULLISH"
            arb_bias = "BUY"
        elif mid_price >= 0.55:
            direction_signal = "MILD_BULLISH"
            arb_bias = "WATCH_BUY"
        elif mid_price <= 0.25:
            direction_signal = "STRONG_BEARISH"
            arb_bias = "AVOID"
        elif mid_price <= 0.45:
            direction_signal = "MILD_BEARISH"
            arb_bias = "CAUTION"
        else:
            direction_signal = "UNCERTAIN"
            arb_bias = "NEUTRAL"

        # High spread = low liquidity = high vol expected
        volatility_signal = "HIGH_VOL_EXPECTED" if spread > 0.05 else \
                            "MODERATE_VOL"      if spread > 0.02 else "LOW_VOL"

        return {
            "market_id":         market_id,
            "title":             market.get("title", ""),
            "yes_probability":   round(mid_price * 100, 1),
            "best_bid":          best_bid,
            "best_ask":          best_ask,
            "spread":            spread,
            "last_price":        last_price,
            "bid_liquidity":     round(bid_liquidity, 2),
            "ask_liquidity":     round(ask_liquidity, 2),
            "total_liquidity":   round(total_liquidity, 2),
            "volume_24h":        volume_24h,
            "direction_signal":  direction_signal,
            "volatility_signal": volatility_signal,
            "arb_bias":          arb_bias,
        }

    def run(self, token: str) -> dict:
        """
        Main entry point: fetch all relevant markets for a token
        and compute an aggregate prediction signal.
        """
        print(f"  🔮 Fetching predict.fun markets for {token}...")
        markets = self.find_token_markets(token)

        if not markets:
            print(f"    No prediction markets found for {token}")
            return {
                "token":            token,
                "markets_found":    0,
                "aggregate_signal": 0.5,
                "prediction_signal": None,
                "direction":        "NO_DATA",
                "arb_bias":         "NEUTRAL",
                "markets":          [],
                "summary":          f"No predict.fun markets found for {token}"
            }

        analyzed = []
        for m in markets[:5]:   # analyze top 5 most relevant
            signal = self.analyze_market_signal(m)
            if signal:
                analyzed.append(signal)

        if not analyzed:
            return {"token": token, "markets_found": 0, "prediction_signal": None,
                    "direction": "NO_DATA", "arb_bias": "NEUTRAL"}

        # ── Aggregate signal across all related markets ──
        avg_yes_prob = sum(a["yes_probability"] for a in analyzed) / len(analyzed)
        total_vol    = sum(a["volume_24h"] for a in analyzed)

        # Weight by volume: high-volume markets are more reliable signals
        if total_vol > 0:
            weighted_prob = sum(
                a["yes_probability"] * (a["volume_24h"] / total_vol)
                for a in analyzed
            )
        else:
            weighted_prob = avg_yes_prob

        # Convert to -1 to +1 scale (same as sentiment signal)
        # 50% = 0 (neutral), 100% = +1 (max bullish), 0% = -1 (max bearish)
        prediction_signal = round((weighted_prob - 50) / 50, 3)

        # Aggregate direction
        bullish_count = sum(1 for a in analyzed if "BULLISH" in a["direction_signal"])
        bearish_count = sum(1 for a in analyzed if "BEARISH" in a["direction_signal"])

        if bullish_count > bearish_count:
            aggregate_direction = "BULLISH"
            arb_bias = "BUY"
        elif bearish_count > bullish_count:
            aggregate_direction = "BEARISH"
            arb_bias = "AVOID"
        else:
            aggregate_direction = "UNCERTAIN"
            arb_bias = "NEUTRAL"

        result = {
            "token":              token,
            "markets_found":      len(analyzed),
            "aggregate_yes_prob": round(weighted_prob, 1),
            "prediction_signal":  prediction_signal,    # -1.0 to +1.0
            "direction":          aggregate_direction,
            "arb_bias":           arb_bias,
            "total_volume_24h":   round(total_vol, 2),
            "markets":            analyzed,
            "summary":            f"{len(analyzed)} markets | Avg YES: {weighted_prob:.1f}% | Signal: {prediction_signal:+.3f} | {aggregate_direction}"
        }

        self._print_summary(result)
        return result

    def _print_summary(self, r: dict):
        bias_icon = "📈" if r["arb_bias"] == "BUY" else "📉" if r["arb_bias"] == "AVOID" else "➡️"
        print(f"""    ┌─ predict.fun: {r['token']} ────────────────────
    │  Markets:  {r['markets_found']} found
    │  YES Prob: {r.get('aggregate_yes_prob', 0):.1f}%
    │  Signal:   {r['prediction_signal']:+.3f}
    │  {bias_icon} Direction: {r['direction']}
    └─ {r['summary']}""")
