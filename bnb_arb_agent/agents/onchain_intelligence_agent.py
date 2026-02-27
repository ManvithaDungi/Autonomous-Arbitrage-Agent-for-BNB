# agents/onchain_intelligence_agent.py
# 🧠 On-Chain Intelligence Agent
# Monitors: Buy/Sell Pressure, Wallet Inflows, Social Growth, Dev Activity,
#           Liquidity Changes, Narrative Keywords, Holder Distribution
# Predicts:  Momentum Building, Distribution Phase, Accumulation Phase, Volatility Spikes

import requests
import time
from datetime import datetime, timedelta
from typing import TypedDict, List, Dict
import pandas as pd
import numpy as np
from config import Config

cfg = Config()

# ═══════════════════════════════════════════════════════════
# 1. BUY/SELL PRESSURE MONITOR
# Uses: CoinGecko OHLCV + DEX trade volume ratio
# ═══════════════════════════════════════════════════════════
class BuySellPressureMonitor:
    COINGECKO_IDS = {
        "BNB": "binancecoin", "CAKE": "pancakeswap-token",
        "BTCB": "bitcoin-bep2", "ETH": "ethereum"
    }

    def fetch(self, token: str) -> dict:
        coin_id = self.COINGECKO_IDS.get(token, token.lower())
        result = {"buy_pressure": 0, "sell_pressure": 0, "ratio": 0, "signal": "NEUTRAL"}

        try:
            # Get OHLCV data (last 1 day, hourly)
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": "1"}
            data = requests.get(url, params=params, timeout=8).json()

            if isinstance(data, list) and len(data) > 2:
                # Buy pressure: candles where close > open
                bullish = [c for c in data if c[4] > c[1]]   # close > open
                bearish = [c for c in data if c[4] <= c[1]]

                buy_vol = sum(c[4] - c[1] for c in bullish)
                sell_vol = sum(c[1] - c[4] for c in bearish)
                total = buy_vol + sell_vol or 1

                result = {
                    "buy_pressure": round(buy_vol / total * 100, 2),
                    "sell_pressure": round(sell_vol / total * 100, 2),
                    "ratio": round(buy_vol / (sell_vol or 1), 3),
                    "signal": "BULLISH" if buy_vol > sell_vol * 1.2 else
                              "BEARISH" if sell_vol > buy_vol * 1.2 else "NEUTRAL"
                }
        except Exception as e:
            print(f"[BuySellPressure Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 2. WALLET INFLOWS MONITOR
# Uses: BscScan API - large wallet transfers (whale tracking)
# ═══════════════════════════════════════════════════════════
class WalletInflowMonitor:
    BSCSCAN_BASE = "https://api.bscscan.com/api"
    # BSC Token contracts
    TOKEN_CONTRACTS = {
        "CAKE": "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",
        "BNB":  "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    }
    WHALE_THRESHOLD_USD = 100_000   # $100K+ = whale move

    def fetch(self, token: str) -> dict:
        result = {
            "whale_inflows": 0, "whale_outflows": 0,
            "large_tx_count": 0, "net_whale_flow": 0,
            "signal": "NEUTRAL"
        }

        contract = self.TOKEN_CONTRACTS.get(token)
        if not contract:
            return result

        try:
            # Get recent large token transfers
            params = {
                "module": "account",
                "action": "tokentx",
                "contractaddress": contract,
                "page": 1, "offset": 100,
                "sort": "desc",
                "apikey": getattr(cfg, 'BSCSCAN_API_KEY', 'YourApiKeyToken')
            }
            data = requests.get(self.BSCSCAN_BASE, params=params, timeout=8).json()
            txs = data.get("result", [])

            if isinstance(txs, list):
                # Get token price for USD value estimate
                price_data = requests.get(
                    f"https://api.coingecko.com/api/v3/simple/price?ids=pancakeswap-token&vs_currencies=usd"
                ).json()
                token_price = list(price_data.values())[0].get("usd", 1) if price_data else 1

                inflows = outflows = 0
                large_count = 0

                for tx in txs[:50]:
                    try:
                        decimals = int(tx.get("tokenDecimal", 18))
                        value = int(tx.get("value", 0)) / (10 ** decimals)
                        usd_value = value * token_price

                        if usd_value >= self.WHALE_THRESHOLD_USD:
                            large_count += 1
                            # Rough heuristic: exchange addresses = outflow from whale
                            inflows += usd_value
                    except:
                        pass

                result = {
                    "whale_inflows": round(inflows, 2),
                    "whale_outflows": round(outflows, 2),
                    "large_tx_count": large_count,
                    "net_whale_flow": round(inflows - outflows, 2),
                    "signal": "ACCUMULATION" if inflows > outflows * 1.3 else
                              "DISTRIBUTION" if outflows > inflows * 1.3 else "NEUTRAL"
                }
        except Exception as e:
            print(f"[WalletInflow Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 3. SOCIAL GROWTH VELOCITY MONITOR
# Uses: Reddit growth + CoinGecko community stats
# ═══════════════════════════════════════════════════════════
class SocialGrowthMonitor:
    COINGECKO_IDS = {
        "BNB": "binancecoin", "CAKE": "pancakeswap-token",
        "BTCB": "bitcoin-bep2", "ETH": "ethereum"
    }

    def fetch(self, token: str) -> dict:
        coin_id = self.COINGECKO_IDS.get(token, token.lower())
        result = {
            "reddit_subscribers": 0, "twitter_followers": 0,
            "telegram_members": 0, "social_score": 0,
            "community_velocity": 0, "signal": "NEUTRAL"
        }

        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            params = {"localization": "false", "tickers": "false",
                      "market_data": "false", "community_data": "true",
                      "developer_data": "false"}
            data = requests.get(url, params=params, timeout=8).json()

            community = data.get("community_data", {})
            reddit_subs = community.get("reddit_subscribers", 0) or 0
            reddit_active = community.get("reddit_accounts_active_48h", 0) or 0
            twitter_followers = community.get("twitter_followers", 0) or 0
            telegram_members = community.get("telegram_channel_user_count", 0) or 0

            # Activity ratio: active/total subscribers = engagement velocity
            activity_ratio = (reddit_active / reddit_subs * 100) if reddit_subs > 0 else 0

            social_score = min(100, int(
                (min(reddit_subs, 500000) / 5000) +
                (activity_ratio * 2) +
                (min(twitter_followers, 1000000) / 10000)
            ))

            result = {
                "reddit_subscribers": reddit_subs,
                "reddit_active_48h": reddit_active,
                "twitter_followers": twitter_followers,
                "telegram_members": telegram_members,
                "activity_ratio_pct": round(activity_ratio, 3),
                "social_score": social_score,
                "signal": "HIGH_ENGAGEMENT" if activity_ratio > 2 else
                          "GROWING" if activity_ratio > 0.5 else "LOW_ENGAGEMENT"
            }
        except Exception as e:
            print(f"[SocialGrowth Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 4. DEV ACTIVITY MONITOR
# Uses: GitHub API - commit frequency, PR activity
# ═══════════════════════════════════════════════════════════
class DevActivityMonitor:
    GITHUB_REPOS = {
        "BNB":  "bnb-chain/bsc",
        "CAKE": "pancakeswap/pancake-frontend",
    }

    def fetch(self, token: str) -> dict:
        repo = self.GITHUB_REPOS.get(token)
        result = {
            "commits_last_week": 0, "open_prs": 0,
            "open_issues": 0, "contributors": 0,
            "last_commit_hours_ago": 999, "signal": "INACTIVE"
        }

        if not repo:
            return result

        try:
            headers = {"Accept": "application/vnd.github.v3+json"}
            api_key = getattr(cfg, 'GITHUB_TOKEN', None)
            if api_key:
                headers["Authorization"] = f"token {api_key}"

            # Commit activity (last week)
            commits_url = f"https://api.github.com/repos/{repo}/commits"
            params = {
                "since": (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z",
                "per_page": 100
            }
            commits = requests.get(commits_url, headers=headers, params=params, timeout=8).json()
            commit_count = len(commits) if isinstance(commits, list) else 0

            # Latest commit time
            last_commit_hours = 999
            if isinstance(commits, list) and commits:
                last_date_str = commits[0].get("commit", {}).get("author", {}).get("date", "")
                if last_date_str:
                    last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00"))
                    last_commit_hours = (datetime.utcnow().replace(tzinfo=last_date.tzinfo) - last_date).total_seconds() / 3600

            # Repo stats
            repo_data = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=8).json()
            open_issues = repo_data.get("open_issues_count", 0)

            result = {
                "commits_last_week": commit_count,
                "open_issues": open_issues,
                "last_commit_hours_ago": round(last_commit_hours, 1),
                "stars": repo_data.get("stargazers_count", 0),
                "signal": "VERY_ACTIVE" if commit_count > 20 else
                          "ACTIVE" if commit_count > 5 else
                          "LOW_ACTIVITY" if commit_count > 0 else "INACTIVE"
            }
        except Exception as e:
            print(f"[DevActivity Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 5. LIQUIDITY CHANGES MONITOR
# Uses: PancakeSwap Subgraph + DeFiLlama
# ═══════════════════════════════════════════════════════════
class LiquidityMonitor:
    DEFILLAMA_BASE = "https://api.llama.fi"
    PANCAKE_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v2"

    PROTOCOL_SLUGS = {
        "CAKE": "pancakeswap",
        "BNB":  "pancakeswap",
    }

    def fetch(self, token: str) -> dict:
        result = {
            "tvl_usd": 0, "tvl_change_24h_pct": 0,
            "pool_liquidity": 0, "liquidity_signal": "NEUTRAL"
        }

        try:
            # DeFiLlama TVL
            protocol = self.PROTOCOL_SLUGS.get(token, "pancakeswap")
            data = requests.get(f"{self.DEFILLAMA_BASE}/protocol/{protocol}", timeout=8).json()

            tvl_data = data.get("tvl", [])
            if tvl_data and len(tvl_data) >= 2:
                current_tvl = tvl_data[-1].get("totalLiquidityUSD", 0)
                prev_tvl = tvl_data[-2].get("totalLiquidityUSD", 0)
                change_pct = ((current_tvl - prev_tvl) / prev_tvl * 100) if prev_tvl > 0 else 0

                result = {
                    "tvl_usd": round(current_tvl, 2),
                    "tvl_change_24h_pct": round(change_pct, 3),
                    "liquidity_signal": "INFLOW" if change_pct > 2 else
                                        "OUTFLOW" if change_pct < -2 else "STABLE"
                }
        except Exception as e:
            print(f"[Liquidity Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 6. NARRATIVE KEYWORD MONITOR
# Uses: Reddit + RSS already fetched — reuses ingestion data
#       Here we do keyword frequency + trend velocity
# ═══════════════════════════════════════════════════════════
class NarrativeKeywordMonitor:
    # Keyword clusters mapped to market phases
    KEYWORD_CLUSTERS = {
        "PUMP_NARRATIVE":     ["moon", "pump", "100x", "gem", "bullish", "breakout", "ath", "parabolic", "send it"],
        "DUMP_NARRATIVE":     ["dump", "rug", "scam", "bearish", "crash", "sell", "exit", "dead", "rekt"],
        "ACCUMULATION":       ["buy the dip", "accumulate", "undervalued", "support", "floor", "hodl", "loading"],
        "LISTING_CATALYST":   ["listing", "listed", "binance list", "exchange", "cex", "announcement", "partnership"],
        "WHALE_NARRATIVE":    ["whale", "large wallet", "big buy", "million", "institution", "fund"],
        "FEAR_NARRATIVE":     ["fear", "uncertain", "worried", "panic", "liquidation", "margin call"],
    }

    def analyze(self, texts: List[str]) -> dict:
        if not texts:
            return {"dominant_narrative": "NONE", "keyword_scores": {}, "signal": "NEUTRAL"}

        combined = " ".join(texts).lower()
        scores = {}

        for narrative, keywords in self.KEYWORD_CLUSTERS.items():
            score = sum(combined.count(kw.lower()) for kw in keywords)
            scores[narrative] = score

        dominant = max(scores, key=scores.get)
        total = sum(scores.values()) or 1

        return {
            "dominant_narrative": dominant,
            "keyword_scores": scores,
            "narrative_confidence": round(scores[dominant] / total * 100, 1),
            "signal": "BULLISH" if dominant in ["PUMP_NARRATIVE", "LISTING_CATALYST", "ACCUMULATION"]
                      else "BEARISH" if dominant in ["DUMP_NARRATIVE", "FEAR_NARRATIVE"]
                      else "WATCHING"
        }


# ═══════════════════════════════════════════════════════════
# 7. HOLDER DISTRIBUTION MONITOR
# Uses: BscScan token holders API
# ═══════════════════════════════════════════════════════════
class HolderDistributionMonitor:
    BSCSCAN_BASE = "https://api.bscscan.com/api"
    TOKEN_CONTRACTS = {
        "CAKE": "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",
    }

    def fetch(self, token: str) -> dict:
        result = {
            "total_holders": 0, "top10_concentration_pct": 0,
            "distribution_signal": "UNKNOWN"
        }

        contract = self.TOKEN_CONTRACTS.get(token)
        if not contract:
            return result

        try:
            params = {
                "module": "token",
                "action": "tokenholderlist",
                "contractaddress": contract,
                "page": 1, "offset": 20,
                "apikey": getattr(cfg, 'BSCSCAN_API_KEY', 'YourApiKeyToken')
            }
            data = requests.get(self.BSCSCAN_BASE, params=params, timeout=8).json()
            holders = data.get("result", [])

            if isinstance(holders, list) and holders:
                values = [float(h.get("TokenHolderQuantity", 0)) for h in holders[:10]]
                total_top10 = sum(values)

                # Get total supply for concentration
                supply_params = {
                    "module": "stats",
                    "action": "tokensupply",
                    "contractaddress": contract,
                    "apikey": getattr(cfg, 'BSCSCAN_API_KEY', 'YourApiKeyToken')
                }
                supply_data = requests.get(self.BSCSCAN_BASE, params=supply_params, timeout=5).json()
                total_supply = float(supply_data.get("result", 1) or 1)

                concentration = total_top10 / total_supply * 100

                result = {
                    "top10_concentration_pct": round(concentration, 2),
                    "distribution_signal": "WHALE_DOMINATED" if concentration > 60 else
                                           "MODERATE_CONCENTRATION" if concentration > 30 else
                                           "DISTRIBUTED"
                }
        except Exception as e:
            print(f"[HolderDistribution Error] {e}")

        return result


# ═══════════════════════════════════════════════════════════
# 🔮 MARKET PHASE PREDICTOR
# Combines all signals → predicts market phase
# ═══════════════════════════════════════════════════════════
class MarketPhasePredictor:

    def predict(self, intelligence: dict) -> dict:
        scores = {
            "MOMENTUM_BUILDING": 0,
            "DISTRIBUTION_PHASE": 0,
            "ACCUMULATION_PHASE": 0,
            "VOLATILITY_SPIKE_INCOMING": 0,
        }

        # Buy/Sell Pressure
        bp = intelligence.get("buy_sell_pressure", {})
        if bp.get("signal") == "BULLISH":
            scores["MOMENTUM_BUILDING"] += 25
        elif bp.get("signal") == "BEARISH":
            scores["DISTRIBUTION_PHASE"] += 20

        # Wallet Inflows
        wi = intelligence.get("wallet_inflows", {})
        if wi.get("signal") == "ACCUMULATION":
            scores["ACCUMULATION_PHASE"] += 30
        elif wi.get("signal") == "DISTRIBUTION":
            scores["DISTRIBUTION_PHASE"] += 30
        if wi.get("large_tx_count", 0) > 5:
            scores["VOLATILITY_SPIKE_INCOMING"] += 20

        # Social Growth
        sg = intelligence.get("social_growth", {})
        if sg.get("signal") == "HIGH_ENGAGEMENT":
            scores["MOMENTUM_BUILDING"] += 20
            scores["VOLATILITY_SPIKE_INCOMING"] += 15

        # Dev Activity
        da = intelligence.get("dev_activity", {})
        if da.get("signal") in ["VERY_ACTIVE", "ACTIVE"]:
            scores["MOMENTUM_BUILDING"] += 15
        elif da.get("signal") == "INACTIVE":
            scores["DISTRIBUTION_PHASE"] += 10

        # Liquidity
        lq = intelligence.get("liquidity", {})
        if lq.get("liquidity_signal") == "INFLOW":
            scores["ACCUMULATION_PHASE"] += 20
        elif lq.get("liquidity_signal") == "OUTFLOW":
            scores["DISTRIBUTION_PHASE"] += 25
            scores["VOLATILITY_SPIKE_INCOMING"] += 10

        # Narrative Keywords
        nk = intelligence.get("narrative_keywords", {})
        narrative = nk.get("dominant_narrative", "")
        if narrative == "LISTING_CATALYST":
            scores["MOMENTUM_BUILDING"] += 30
            scores["VOLATILITY_SPIKE_INCOMING"] += 25
        elif narrative == "PUMP_NARRATIVE":
            scores["MOMENTUM_BUILDING"] += 20
        elif narrative == "ACCUMULATION":
            scores["ACCUMULATION_PHASE"] += 25
        elif narrative in ["DUMP_NARRATIVE", "FEAR_NARRATIVE"]:
            scores["DISTRIBUTION_PHASE"] += 25

        # Holder Distribution
        hd = intelligence.get("holder_distribution", {})
        if hd.get("distribution_signal") == "WHALE_DOMINATED":
            scores["VOLATILITY_SPIKE_INCOMING"] += 20
            scores["DISTRIBUTION_PHASE"] += 15

        predicted_phase = max(scores, key=scores.get)
        confidence = scores[predicted_phase]

        # Normalize
        total = sum(scores.values()) or 1
        phase_probs = {k: round(v / total * 100, 1) for k, v in scores.items()}

        return {
            "predicted_phase": predicted_phase,
            "confidence": min(confidence, 100),
            "phase_probabilities": phase_probs,
            "recommendation": self._get_recommendation(predicted_phase, confidence),
            "risk_level": "HIGH" if scores["VOLATILITY_SPIKE_INCOMING"] > 40 else
                          "MEDIUM" if scores["VOLATILITY_SPIKE_INCOMING"] > 20 else "LOW"
        }

    def _get_recommendation(self, phase: str, confidence: int) -> str:
        recs = {
            "MOMENTUM_BUILDING":       "📈 WATCH FOR ENTRY — Momentum building, consider small position",
            "DISTRIBUTION_PHASE":      "🚨 CAUTION — Whales may be distributing, avoid buying",
            "ACCUMULATION_PHASE":      "💎 POTENTIAL OPPORTUNITY — Smart money accumulating",
            "VOLATILITY_SPIKE_INCOMING": "⚡ HIGH VOLATILITY EXPECTED — Reduce position size, widen stop-loss"
        }
        suffix = f" (Confidence: {confidence}/100)"
        return recs.get(phase, "🔍 MONITORING") + suffix


# ═══════════════════════════════════════════════════════════
# 🧠 MASTER ON-CHAIN INTELLIGENCE AGENT
# ═══════════════════════════════════════════════════════════
class OnChainIntelligenceAgent:
    def __init__(self):
        self.buy_sell = BuySellPressureMonitor()
        self.wallet = WalletInflowMonitor()
        self.social = SocialGrowthMonitor()
        self.dev = DevActivityMonitor()
        self.liquidity = LiquidityMonitor()
        self.narrative = NarrativeKeywordMonitor()
        self.holder = HolderDistributionMonitor()
        self.predictor = MarketPhasePredictor()

    def run(self, token: str, texts: List[str] = None) -> dict:
        print(f"\n🧠 Running On-Chain Intelligence for {token}...")

        intelligence = {}

        print("  📊 Buy/Sell Pressure...")
        intelligence["buy_sell_pressure"] = self.buy_sell.fetch(token)

        print("  🐋 Wallet Inflows...")
        intelligence["wallet_inflows"] = self.wallet.fetch(token)

        print("  📱 Social Growth...")
        intelligence["social_growth"] = self.social.fetch(token)

        print("  👨‍💻 Dev Activity...")
        intelligence["dev_activity"] = self.dev.fetch(token)

        print("  💧 Liquidity Changes...")
        intelligence["liquidity"] = self.liquidity.fetch(token)

        print("  📰 Narrative Keywords...")
        intelligence["narrative_keywords"] = self.narrative.analyze(texts or [])

        print("  👥 Holder Distribution...")
        intelligence["holder_distribution"] = self.holder.fetch(token)

        print("  🔮 Predicting Market Phase...")
        prediction = self.predictor.predict(intelligence)

        result = {
            "token": token,
            "timestamp": datetime.utcnow().isoformat(),
            "intelligence": intelligence,
            "prediction": prediction
        }

        self._print_summary(result)
        return result

    def _print_summary(self, result: dict):
        pred = result["prediction"]
        intel = result["intelligence"]
        token = result["token"]

        print(f"""
╔══════════════════════════════════════════════════════╗
  🧠 ON-CHAIN INTELLIGENCE REPORT: {token}
  ─────────────────────────────────────────────────────
  📊 Buy/Sell:    {intel['buy_sell_pressure'].get('signal')} (ratio: {intel['buy_sell_pressure'].get('ratio')})
  🐋 Whales:      {intel['wallet_inflows'].get('signal')} | Large TXs: {intel['wallet_inflows'].get('large_tx_count')}
  📱 Social:      {intel['social_growth'].get('signal')} | Score: {intel['social_growth'].get('social_score')}/100
  👨‍💻 Dev:         {intel['dev_activity'].get('signal')} | Commits/wk: {intel['dev_activity'].get('commits_last_week')}
  💧 Liquidity:   {intel['liquidity'].get('liquidity_signal')} | TVL Δ: {intel['liquidity'].get('tvl_change_24h_pct')}%
  📰 Narrative:   {intel['narrative_keywords'].get('dominant_narrative')}
  👥 Holders:     {intel['holder_distribution'].get('distribution_signal')}
  ─────────────────────────────────────────────────────
  🔮 PHASE:       {pred['predicted_phase']}
  🎯 CONFIDENCE:  {pred['confidence']}/100
  ⚠️  RISK:        {pred['risk_level']}
  💡 ACTION:      {pred['recommendation']}
╚══════════════════════════════════════════════════════╝
""")
