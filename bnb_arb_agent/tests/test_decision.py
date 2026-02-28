"""Units tests for the decision agent logic."""

import pytest
from unittest.mock import MagicMock, patch

from agents.decision_agent import (
    _compute_confidence,
    _determine_action,
    _parse_gemini,
    DecisionAgent,
)


class TestParseGemini:
    def test_parses_arb_opportunity_yes(self):
        text = "SIGNAL_TYPE: PUMP_INCOMING\nURGENCY: HIGH\nARB_OPPORTUNITY: YES"
        _, _, arb = _parse_gemini(text)
        assert arb is True

    def test_parses_arb_opportunity_no(self):
        _, _, arb = _parse_gemini("ARB_OPPORTUNITY: NO")
        assert arb is False

    def test_parses_urgency(self):
        _, urgency, _ = _parse_gemini("URGENCY: HIGH")
        assert urgency == "HIGH"

    def test_defaults_on_empty_input(self):
        signal_type, urgency, arb = _parse_gemini("")
        assert signal_type == "STABLE"
        assert urgency     == "LOW"
        assert arb is False


class TestComputeConfidence:
    def test_increases_with_momentum_phase(self):
        base = _compute_confidence(0.0, 0.0, "LOW", False, "UNKNOWN",  "MEDIUM")
        with_momentum = _compute_confidence(0.0, 0.0, "LOW", False, "MOMENTUM_BUILDING", "MEDIUM")
        assert with_momentum > base

    def test_decreases_with_distribution_phase(self):
        base = _compute_confidence(0.4, 0.02, "MEDIUM", True, "UNKNOWN",       "MEDIUM")
        dist = _compute_confidence(0.4, 0.02, "MEDIUM", True, "DISTRIBUTION_PHASE", "MEDIUM")
        assert dist < base

    def test_clamped_to_100(self):
        score = _compute_confidence(1.0, 0.5, "HIGH", True, "MOMENTUM_BUILDING", "LOW")
        assert score <= 100

    def test_clamped_to_zero(self):
        score = _compute_confidence(0.0, 0.0, "LOW", False, "DISTRIBUTION_PHASE", "HIGH")
        assert score >= 0


class TestDetermineAction:
    def test_hold_when_no_arb(self):
        assert _determine_action(False, 80, 0.5, "LOW") == "HOLD"

    def test_hold_when_low_confidence(self):
        assert _determine_action(True, 10, 0.5, "LOW") == "HOLD"

    def test_hold_when_high_risk_low_confidence(self):
        assert _determine_action(True, 55, 0.5, "HIGH") == "HOLD"

    def test_execute_trade_at_high_confidence(self):
        assert _determine_action(True, 75, 0.6, "LOW") == "EXECUTE_TRADE"

    def test_paper_trade_at_medium_confidence(self):
        assert _determine_action(True, 40, 0.1, "LOW") == "PAPER_TRADE"


class TestDecisionAgentIntegration:
    @patch("agents.decision_agent._cex_price", return_value={"price": 600.0, "change_24h": 0.5})
    @patch("tools.price_fetcher.DEXPriceFetcher.get_dex_price", return_value=591.0)
    def test_produces_execute_trade_on_clear_arb(self, _mock_dex, _mock_cex, mock_analysis_result, mock_intel_result):
        agent  = DecisionAgent(use_testnet=False)
        agent._execution_agent = MagicMock()

        import os
        os.environ["EXECUTION_ENABLED"] = "false"

        result = agent.evaluate_with_intelligence(mock_analysis_result, mock_intel_result, "BNB")
        assert result["arb_confirmed"] is True
        assert result["action"] in ("EXECUTE_TRADE", "PAPER_TRADE")
        assert result["price_diff_pct"] == pytest.approx(1.5, abs=0.01)

    @patch("agents.decision_agent._cex_price", return_value={"price": 600.0, "change_24h": 0.0})
    @patch("tools.price_fetcher.DEXPriceFetcher.get_dex_price", return_value=0.0)
    def test_holds_when_dex_price_unavailable(self, _mock_dex, _mock_cex, mock_analysis_result):
        agent  = DecisionAgent(use_testnet=False)
        result = agent.evaluate(mock_analysis_result, "BNB")
        assert result["dex_price"] == 0.0
