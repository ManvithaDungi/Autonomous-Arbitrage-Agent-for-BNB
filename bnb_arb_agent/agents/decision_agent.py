# agents/decision_agent.py

import requests
from web3 import Web3
from config import Config
import pandas as pd
from datetime import datetime

cfg = Config()

# ─── Price Fetcher (CoinGecko + PancakeSwap) ───
class PriceFetcher:
    COINGECKO_IDS = {
        "BNB": "binancecoin", "CAKE": "pancakeswap-token",
        "BTCB": "bitcoin-bep2", "ETH": "ethereum",
        "BabyDoge": "baby-doge-coin"
    }
    HEADERS = {"User-Agent": "Mozilla/5.0 (BNBArbAgent/1.0)", "Accept": "application/json"}

    def get_cex_price(self, token):
        """CEX price via CoinGecko (free, no key)"""
        coin_id = self.COINGECKO_IDS.get(token, token.lower())
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
            data = requests.get(url, headers=self.HEADERS, timeout=10).json()
            price_data = data.get(coin_id, {})
            price = price_data.get("usd", 0)
            print(f"  [CoinGecko] {token} ({coin_id}): ${price}")
            return {
                "price": price,
                "change_24h": price_data.get("usd_24h_change", 0)
            }
        except Exception as e:
            print(f"  [CoinGecko Error] {token}: {e}")
            return {"price": 0, "change_24h": 0}

    def get_dex_price_pancakeswap(self, token_symbol):
        """DEX price via PancakeSwap API"""
        TOKEN_ADDRESSES = {
            "CAKE": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
            "BNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        }
        token_addr = TOKEN_ADDRESSES.get(token_symbol, "")
        if not token_addr:
            return 0

        try:
            # Use PancakeSwap token API
            url = f"https://pancakeswap.finance/api/v3/price/list?addresses={token_addr}&chainId=56"
            res = requests.get(url, headers=self.HEADERS, timeout=10).json()
            price = float(res.get(token_addr, res.get(token_addr.lower(), 0)))
            print(f"  [PancakeSwap] {token_symbol}: ${price}")
            return price
        except Exception as e:
            print(f"  [PancakeSwap Error] {token_symbol}: {e}")
            return 0


# ─── Decision Agent ───
class DecisionAgent:
    def __init__(self):
        self.price_fetcher = PriceFetcher()
        self.trade_history = []

    def evaluate(self, analysis_result: dict, token: str) -> dict:
        final_signal = analysis_result.get("final_signal", 0)
        gemini_analysis = analysis_result.get("gemini_analysis", "")

        # Parse Gemini outputs
        signal_type = "STABLE"
        urgency = "LOW"
        arb_opportunity = False

        for line in gemini_analysis.split("\n"):
            if "SIGNAL_TYPE:" in line:
                signal_type = line.split(":", 1)[1].strip()
            if "URGENCY:" in line:
                urgency = line.split(":", 1)[1].strip()
            if "ARB_OPPORTUNITY:" in line:
                arb_opportunity = "YES" in line

        # Fetch prices
        cex_data = self.price_fetcher.get_cex_price(token)
        dex_price = self.price_fetcher.get_dex_price_pancakeswap(token)
        cex_price = cex_data["price"]

        price_diff_pct = 0
        direction = "NONE"
        if cex_price > 0 and dex_price > 0:
            price_diff_pct = abs(cex_price - dex_price) / cex_price
            direction = "BUY_DEX_SELL_CEX" if dex_price < cex_price else "BUY_CEX_SELL_DEX"

        # ─── Decision Logic ───
        # Criteria: Sentiment signal + price diff + Gemini confirmation
        sentiment_trigger = abs(final_signal) > cfg.SENTIMENT_THRESHOLD
        price_trigger = price_diff_pct > cfg.PRICE_DIFF_THRESHOLD
        arb_confirmed = arb_opportunity or (sentiment_trigger and price_trigger)

        # Risk-adjusted score (0-100)
        confidence = min(100, int(
            (abs(final_signal) * 40) +
            (price_diff_pct * 1000) +
            (20 if urgency == "HIGH" else 10 if urgency == "MEDIUM" else 0) +
            (10 if arb_opportunity else 0)
        ))

        decision = {
            "token": token,
            "timestamp": datetime.utcnow().isoformat(),
            "cex_price": cex_price,
            "dex_price": dex_price,
            "price_diff_pct": round(price_diff_pct * 100, 3),
            "direction": direction,
            "sentiment_signal": final_signal,
            "signal_type": signal_type,
            "urgency": urgency,
            "arb_confirmed": arb_confirmed,
            "confidence_score": confidence,
            "action": self._determine_action(arb_confirmed, confidence, final_signal),
            "reason": f"Sentiment={final_signal:.3f}, PriceDiff={price_diff_pct*100:.2f}%, Type={signal_type}"
        }

        self.trade_history.append(decision)
        self._print_decision(decision)
        return decision

    def _determine_action(self, arb_confirmed, confidence, signal):
        if not arb_confirmed or confidence < 30:
            return "HOLD"
        if confidence >= 70 and abs(signal) > 0.5:
            return "EXECUTE_TRADE"
        if confidence >= 40:
            return "PAPER_TRADE"  # Simulate only
        return "MONITOR"

    def _print_decision(self, d):
        print(f"""
╔══════════════════════════════════════╗
  🎯 DECISION: {d['token']}
  CEX: ${d['cex_price']:.4f} | DEX: ${d['dex_price']:.4f}
  Price Diff: {d['price_diff_pct']}%
  Sentiment: {d['sentiment_signal']}
  Signal: {d['signal_type']} [{d['urgency']}]
  Confidence: {d['confidence_score']}/100
  ➡️  ACTION: {d['action']}
  Reason: {d['reason']}
╚══════════════════════════════════════╝
""")