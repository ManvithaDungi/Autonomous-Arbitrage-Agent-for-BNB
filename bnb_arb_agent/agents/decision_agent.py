"""Arbitrage decision engine — evaluates sentiment and price signals to produce a trade action."""

from datetime import datetime
from typing import Optional

import requests

from agents.execution_agent import ExecutionAgent
from config import Config
from core.constants import COINGECKO_IDS
from core.logger import get_logger
from tools.price_fetcher import DEXPriceFetcher

logger = get_logger(__name__)
config = Config()

_CEX_URL = "https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"


def _cex_price(token: str) -> dict:
    coin_id = COINGECKO_IDS.get(token, token.lower())
    try:
        response = requests.get(_CEX_URL.format(coin_id=coin_id), timeout=6)
        response.raise_for_status()
        data = response.json().get(coin_id, {})
        return {"price": data.get("usd", 0.0), "change_24h": data.get("usd_24h_change", 0.0)}
    except Exception:
        logger.warning("CEX price fetch failed for %s.", token)
        return {"price": 0.0, "change_24h": 0.0}


def _parse_gemini(analysis_text: str) -> tuple[str, str, bool]:
    """Extract signal_type, urgency, and arb_opportunity from Gemini output."""
    signal_type    = "STABLE"
    urgency        = "LOW"
    arb_opportunity = False

    for line in analysis_text.split("\n"):
        if "SIGNAL_TYPE:" in line:
            signal_type = line.split(":", 1)[1].strip()
        elif "URGENCY:" in line:
            urgency = line.split(":", 1)[1].strip()
        elif "ARB_OPPORTUNITY:" in line:
            arb_opportunity = "YES" in line

    return signal_type, urgency, arb_opportunity


def _compute_confidence(
    signal:          float,
    price_diff:      float,
    urgency:         str,
    arb_opportunity: bool,
    phase:           str,
    risk_level:      str,
) -> int:
    base = int(
        (abs(signal) * 40)
        + (price_diff * 1000)
        + (20 if urgency == "HIGH" else 10 if urgency == "MEDIUM" else 0)
        + (10 if arb_opportunity else 0)
    )

    phase_adjustments = {
        "MOMENTUM_BUILDING":        20,
        "ACCUMULATION_PHASE":       15,
        "DISTRIBUTION_PHASE":      -25,
        "VOLATILITY_SPIKE_INCOMING": 10,
    }
    risk_adjustments = {"HIGH": -10, "LOW": 5}

    adjusted = base + phase_adjustments.get(phase, 0) + risk_adjustments.get(risk_level, 0)
    return max(0, min(100, adjusted))


def _determine_action(arb_confirmed: bool, confidence: int, signal: float, risk_level: str) -> str:
    if risk_level == "HIGH" and confidence < 60:
        return "HOLD"
    if not arb_confirmed or confidence < 20:
        return "HOLD"
    if confidence >= 60:
        return "EXECUTE_TRADE"
    if confidence >= 30:
        return "PAPER_TRADE"
    return "MONITOR"


class DecisionAgent:
    """Computes an arbitrage decision from sentiment analysis and on-chain intelligence."""

    def __init__(self, use_testnet: bool = False) -> None:
        self._dex_fetcher     = DEXPriceFetcher(use_testnet=use_testnet)
        self._execution_agent = ExecutionAgent(config.mcp_server_url)
        self.trade_history: list[dict] = []

    def evaluate(self, analysis_result: dict, token: str) -> dict:
        """Backwards-compatible wrapper — delegates to evaluate_with_intelligence."""
        return self.evaluate_with_intelligence(analysis_result, None, token)

    def evaluate_with_intelligence(
        self,
        analysis_result: dict,
        intel_result:    Optional[dict],
        token:           str,
    ) -> dict:
        """Produce an arbitrage decision enriched with on-chain intelligence data.

        Args:
            analysis_result: Output from AnalysisAgent.run().
            intel_result:    Output from OnChainIntelligenceAgent.run(), or None.
            token:           Token symbol (e.g. 'BNB').

        Returns:
            Decision dict with action, confidence, prices, and optional execution result.
        """
        final_signal = analysis_result.get("final_signal", 0.0)
        signal_type, urgency, arb_opportunity = _parse_gemini(
            analysis_result.get("gemini_analysis", "")
        )

        cex_data  = _cex_price(token)
        cex_price = cex_data["price"]
        dex_price = self._dex_fetcher.get_dex_price(token)

        price_diff = 0.0
        direction  = "NONE"
        if cex_price > 0 and dex_price > 0:
            price_diff = abs(cex_price - dex_price) / cex_price
            direction  = "BUY_DEX_SELL_CEX" if dex_price < cex_price else "BUY_CEX_SELL_DEX"

        phase              = "UNKNOWN"
        risk_level         = "MEDIUM"
        intel_recommendation = ""

        if intel_result:
            pred               = intel_result.get("prediction", {})
            phase              = pred.get("predicted_phase", "UNKNOWN")
            risk_level         = pred.get("risk_level", "MEDIUM")
            intel_recommendation = pred.get("recommendation", "")

        confidence = _compute_confidence(final_signal, price_diff, urgency, arb_opportunity, phase, risk_level)

        sentiment_trigger = abs(final_signal) > config.sentiment_threshold
        price_trigger     = price_diff > config.price_diff_threshold

        arb_confirmed = (
            (sentiment_trigger and price_trigger)
            or (arb_opportunity and confidence > 30)
            or (price_diff > 0.005 and dex_price > 0)
            or (phase == "MOMENTUM_BUILDING" and price_diff > 0.003)
        )

        action = _determine_action(arb_confirmed, confidence, final_signal, risk_level)

        decision = {
            "token":               token,
            "timestamp":           datetime.utcnow().isoformat(),
            "cex_price":           cex_price,
            "dex_price":           dex_price,
            "price_diff_pct":      round(price_diff * 100, 3),
            "direction":           direction,
            "sentiment_signal":    final_signal,
            "signal_type":         signal_type,
            "urgency":             urgency,
            "market_phase":        phase,
            "risk_level":          risk_level,
            "arb_confirmed":       arb_confirmed,
            "confidence_score":    confidence,
            "action":              action,
            "intel_recommendation": intel_recommendation,
            "reason":              (
                f"Sentiment={final_signal:.3f} | "
                f"PriceDiff={price_diff * 100:.2f}% | "
                f"Phase={phase} | Risk={risk_level}"
            ),
        }

        self.trade_history.append(decision)
        self._log_decision(decision)

        if action == "EXECUTE_TRADE":
            if config.execution_enabled:
                logger.info("EXECUTE_TRADE triggered — routing to ExecutionAgent.")
                decision["execution_result"] = self._execution_agent.execute(decision)
            else:
                logger.info("EXECUTE_TRADE triggered but execution is disabled.")
                decision["execution_result"] = {"status": "DISABLED"}

        return decision

    def _log_decision(self, decision: dict) -> None:
        action = decision["action"]
        logger.info(
            "[%s] CEX=%.4f DEX=%.4f diff=%.3f%% signal=%+.3f confidence=%d/100 -> %s",
            decision["token"],
            decision["cex_price"],
            decision["dex_price"],
            decision["price_diff_pct"],
            decision["sentiment_signal"],
            decision["confidence_score"],
            action,
        )