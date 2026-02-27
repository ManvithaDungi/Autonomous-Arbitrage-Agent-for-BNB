"""
simulate.py — Dry-run the full arb agent pipeline with MOCKED prices.
No testnet, no wallet, no real transactions.

Usage:
    .venv\Scripts\python.exe simulate.py
    .venv\Scripts\python.exe simulate.py --spread 2.5   # simulate 2.5% price diff
"""
import sys, argparse
sys.path.insert(0, '.')

# ── Parse args ──
parser = argparse.ArgumentParser()
parser.add_argument("--spread", type=float, default=1.2,
                    help="Simulated DEX vs CEX price spread %% (default: 1.2)")
parser.add_argument("--token", type=str, default="BNB",
                    help="Token to simulate (default: BNB)")
parser.add_argument("--sentiment", type=float, default=0.25,
                    help="Simulated Gemini sentiment (-1 to +1, default: 0.25)")
args = parser.parse_args()

TOKEN   = args.token
SPREAD  = args.spread / 100   # convert % to decimal
SENT    = args.sentiment

print(f"""
╔══════════════════════════════════════════════════════╗
  🧪 BNB ARB AGENT — SIMULATION MODE (no blockchain)
  Token:     {TOKEN}
  Spread:    {args.spread}% (DEX cheaper than CEX)
  Sentiment: {SENT:+.2f}
╚══════════════════════════════════════════════════════╝
""")

# ── Step 1: Mock analysis result (skip real Gemini + news fetch) ──
mock_analysis = {
    "final_signal": SENT,
    "vader_scores": [SENT] * 5,
    "gemini_analysis": (
        f"SENTIMENT: {SENT}\n"
        "SIGNAL_TYPE: PUMP_INCOMING\n"
        "URGENCY: MEDIUM\n"
        "KEY_INSIGHT: Simulated bullish momentum for testing.\n"
        "ARB_OPPORTUNITY: YES\n"
    ),
    "summary": f"Simulated | signal={SENT}"
}

# ── Step 2: Mock intel result (skip on-chain intelligence) ──
mock_intel = {
    "prediction": {
        "predicted_phase":   "MOMENTUM_BUILDING",
        "risk_level":        "LOW",
        "confidence":        72,
        "recommendation":    "Simulated: momentum detected, arb window open.",
        "phase_probabilities": {
            "MOMENTUM_BUILDING":        72,
            "ACCUMULATION_PHASE":       15,
            "DISTRIBUTION_PHASE":        8,
            "VOLATILITY_SPIKE_INCOMING": 5,
        }
    },
    "intelligence": {}
}

# ── Step 3: Patch DEXPriceFetcher to return a mocked price with known spread ──
from unittest.mock import patch
import requests

# Get real CEX price from CoinGecko
COINGECKO_IDS = {
    "BNB": "binancecoin", "CAKE": "pancakeswap-token",
    "BTCB": "bitcoin-bep2", "ETH": "ethereum", "BabyDoge": "baby-doge-coin"
}
coin_id = COINGECKO_IDS.get(TOKEN, TOKEN.lower())
try:
    resp = requests.get(
        f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd",
        timeout=6
    ).json()
    cex_price = resp.get(coin_id, {}).get("usd", 600.0)
except Exception:
    cex_price = 600.0  # fallback

dex_price = cex_price * (1 - SPREAD)   # DEX is cheaper by SPREAD%

print(f"  📈 CEX price (CoinGecko): ${cex_price:.4f}")
print(f"  💱 DEX price (mocked):    ${dex_price:.4f}")
print(f"  📊 Simulated spread:      {SPREAD*100:.2f}%\n")

# ── Step 4: Run decision agent with mocked prices ──
from agents.decision_agent import DecisionAgent

# Monkey-patch DEXPriceFetcher.get_dex_price
from tools import price_fetcher
original_get = price_fetcher.DEXPriceFetcher.get_dex_price
price_fetcher.DEXPriceFetcher.get_dex_price = lambda self, sym: dex_price if sym == TOKEN else 0.0

agent = DecisionAgent(use_testnet=False)

# Also patch CEX price inside decision_agent
import agents.decision_agent as da
original_cex = da.get_cex_price
da.get_cex_price = lambda tok: {"price": cex_price, "change_24h": 0.5} if tok == TOKEN else {"price": 0, "change_24h": 0}

# Disable actual MCP execution
import os
os.environ["EXECUTION_ENABLED"] = "false"

print("Running decision pipeline...")
result = agent.evaluate_with_intelligence(mock_analysis, mock_intel, TOKEN)

# Restore patches
price_fetcher.DEXPriceFetcher.get_dex_price = original_get
da.get_cex_price = original_cex

# ── Step 5: Show simulation result ──
print(f"""
╔══════════════════════════════════════════════════════╗
  🎯 SIMULATION RESULT
  Token:          {result['token']}
  CEX:            ${result['cex_price']:.4f}
  DEX (mock):     ${result['dex_price']:.4f}
  Price Diff:     {result['price_diff_pct']}%
  Sentiment:      {result['sentiment_signal']:+.3f}
  Confidence:     {result['confidence_score']}/100
  Arb Confirmed:  {result['arb_confirmed']}
  Market Phase:   {result['market_phase']}
  ➡  ACTION:      {result['action']}
  Reason:         {result['reason']}
╚══════════════════════════════════════════════════════╝

{'✅ TRADE WOULD EXECUTE (paper mode — no real tx sent)' if result['action'] in ['EXECUTE_TRADE','PAPER_TRADE'] else '💤 HOLD — thresholds not met'}

To test different scenarios:
  Tiny spread (no trade):   python simulate.py --spread 0.1
  Realistic spread (trade): python simulate.py --spread 1.5
  Bearish sentiment:        python simulate.py --spread 1.5 --sentiment -0.4
  CAKE token:               python simulate.py --token CAKE --spread 2.0
""")
