# agents/decision_agent.py (UPDATED)
# Now uses On-Chain Intelligence + MCP Execution Agent

import requests
from datetime import datetime
from config import Config
from tools.price_fetcher import DEXPriceFetcher
from agents.execution_agent import ExecutionAgent

cfg = Config()

COINGECKO_IDS = {
    "BNB": "binancecoin", "CAKE": "pancakeswap-token",
    "BTCB": "bitcoin-bep2", "ETH": "ethereum",
    "BabyDoge": "baby-doge-coin"
}

def get_cex_price(token):
    coin_id = COINGECKO_IDS.get(token, token.lower())
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        data = requests.get(url, timeout=6).json()
        price_data = data.get(coin_id, {})
        return {
            "price": price_data.get("usd", 0),
            "change_24h": price_data.get("usd_24h_change", 0)
        }
    except:
        return {"price": 0, "change_24h": 0}


class DecisionAgent:
    def __init__(self, use_testnet=False):
        self.dex_fetcher = DEXPriceFetcher(use_testnet=use_testnet)
        self.trade_history = []
        self.use_testnet = use_testnet
        self.execution_agent = ExecutionAgent(cfg.MCP_SERVER_URL)

    def evaluate(self, analysis_result: dict, token: str) -> dict:
        """Original evaluate (backwards compatible)"""
        return self.evaluate_with_intelligence(analysis_result, None, token)

    def evaluate_with_intelligence(self, analysis_result: dict, intel_result: dict, token: str) -> dict:
        """Enhanced evaluate using on-chain intelligence"""

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

        # Fetch prices — CEX from CoinGecko, DEX from PancakeSwap (3 fallback methods)
        cex_data = get_cex_price(token)
        cex_price = cex_data["price"]
        dex_price = self.dex_fetcher.get_dex_price(token)

        price_diff_pct = 0
        direction = "NONE"
        if cex_price > 0 and dex_price > 0:
            price_diff_pct = abs(cex_price - dex_price) / cex_price
            direction = "BUY_DEX_SELL_CEX" if dex_price < cex_price else "BUY_CEX_SELL_DEX"

        # ── Base confidence from sentiment + price ──
        sentiment_trigger = abs(final_signal) > cfg.SENTIMENT_THRESHOLD
        price_trigger = price_diff_pct > cfg.PRICE_DIFF_THRESHOLD

        confidence = int(
            (abs(final_signal) * 40) +
            (price_diff_pct * 1000) +
            (20 if urgency == "HIGH" else 10 if urgency == "MEDIUM" else 0) +
            (10 if arb_opportunity else 0)
        )

        # ── Boost/penalize confidence using on-chain intelligence ──
        phase = "UNKNOWN"
        risk_level = "MEDIUM"
        intel_recommendation = ""

        if intel_result:
            pred = intel_result.get("prediction", {})
            phase = pred.get("predicted_phase", "UNKNOWN")
            risk_level = pred.get("risk_level", "MEDIUM")
            intel_recommendation = pred.get("recommendation", "")
            intel_confidence = pred.get("confidence", 0)

            # Phase-based confidence adjustment
            if phase == "MOMENTUM_BUILDING":
                confidence += 20   # boost arb signals during momentum
            elif phase == "ACCUMULATION_PHASE":
                confidence += 15   # good time to enter
            elif phase == "DISTRIBUTION_PHASE":
                confidence -= 25   # whales selling, reduce confidence
            elif phase == "VOLATILITY_SPIKE_INCOMING":
                confidence += 10   # vol = arb opportunity but risky

            # Risk-based penalty
            if risk_level == "HIGH":
                confidence -= 10
            elif risk_level == "LOW":
                confidence += 5

        confidence = max(0, min(100, confidence))
        arb_confirmed = (sentiment_trigger and price_trigger) or \
                        (arb_opportunity and confidence > 40) or \
                        (phase == "MOMENTUM_BUILDING" and price_diff_pct > 0.005)

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
            "market_phase": phase,
            "risk_level": risk_level,
            "arb_confirmed": arb_confirmed,
            "confidence_score": confidence,
            "action": self._determine_action(arb_confirmed, confidence, final_signal, risk_level),
            "intel_recommendation": intel_recommendation,
            "reason": f"Sentiment={final_signal:.3f} | PriceDiff={price_diff_pct*100:.2f}% | Phase={phase} | Risk={risk_level}"
        }

        self.trade_history.append(decision)
        self._print_decision(decision)

        # ── Execute trade via MCP if action is EXECUTE_TRADE ──
        if decision["action"] == "EXECUTE_TRADE" and cfg.EXECUTION_ENABLED:
            print("\n  ⚡ EXECUTE_TRADE triggered — routing to Execution Agent...")
            execution_result = self.execution_agent.execute(decision)
            decision["execution_result"] = execution_result
        elif decision["action"] == "EXECUTE_TRADE" and not cfg.EXECUTION_ENABLED:
            print("\n  ⏸️  EXECUTE_TRADE triggered but execution is DISABLED (set EXECUTION_ENABLED=true)")
            decision["execution_result"] = {"status": "DISABLED", "reason": "EXECUTION_ENABLED=false"}

        return decision

    def _determine_action(self, arb_confirmed, confidence, signal, risk_level="MEDIUM"):
        if risk_level == "HIGH" and confidence < 70:
            return "HOLD"  # Don't trade in high risk unless very confident
        if not arb_confirmed or confidence < 30:
            return "HOLD"
        if confidence >= 70 and abs(signal) > 0.5:
            return "EXECUTE_TRADE"
        if confidence >= 40:
            return "PAPER_TRADE"
        return "MONITOR"

    def _print_decision(self, d):
        action_icon = "🟢" if d["action"] == "EXECUTE_TRADE" else \
                      "🟡" if d["action"] == "PAPER_TRADE" else "🔴"
        print(f"""
  ┌─ DECISION: {d['token']} ─────────────────────────────
  │  Price:    CEX ${d['cex_price']:.4f} | DEX ${d['dex_price']:.4f} | Δ {d['price_diff_pct']}%
  │  Signal:   {d['sentiment_signal']:+.3f} [{d['signal_type']}] [{d['urgency']}]
  │  Phase:    {d['market_phase']} | Risk: {d['risk_level']}
  │  Score:    {d['confidence_score']}/100
  │  {action_icon} ACTION: {d['action']}
  └─ {d['reason']}
""")