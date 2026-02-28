"""Shared fixtures for the arb agent test suite."""

import pytest


@pytest.fixture
def mock_analysis_result():
    return {
        "final_signal":    0.4,
        "gemini_analysis": (
            "SENTIMENT: 0.4\n"
            "SIGNAL_TYPE: PUMP_INCOMING\n"
            "URGENCY: MEDIUM\n"
            "KEY_INSIGHT: Bullish momentum detected.\n"
            "ARB_OPPORTUNITY: YES\n"
        ),
        "summary": "signal=0.4",
    }


@pytest.fixture
def mock_intel_result():
    return {
        "prediction": {
            "predicted_phase":    "MOMENTUM_BUILDING",
            "risk_level":         "LOW",
            "confidence":         72,
            "recommendation":     "Enter position.",
            "phase_probabilities": {"MOMENTUM_BUILDING": 72},
        },
        "intelligence": {},
    }
