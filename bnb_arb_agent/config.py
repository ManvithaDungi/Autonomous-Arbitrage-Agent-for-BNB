# config.py — Single merged Config with all settings
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Reddit ──
    REDDIT_CLIENT_ID  = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_SECRET     = os.getenv("REDDIT_SECRET", "")
    REDDIT_USER_AGENT = "BNBArb/1.0"

    # ── News APIs ──
    NEWSAPI_KEY      = os.getenv("NEWSAPI_KEY", "")
    GNEWS_KEY        = os.getenv("GNEWS_KEY", "")
    THENEWSAPI_KEY   = os.getenv("THENEWSAPI_KEY", "")

    # CryptoPanic
    CRYPTOPANIC_KEY  = os.getenv("CRYPTOPANIC_KEY", "")

    # ── Twitter ──
    TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

    # ── Gemini ──
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

    # ── On-Chain APIs ──
    BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "YourApiKeyToken")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

    # ── MCP Server (bnbchain-mcp) ──
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:3000")
    WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")

    # ── Execution Settings ──
    TRADE_AMOUNT_BNB = float(os.getenv("TRADE_AMOUNT_BNB", "0.01"))
    MIN_PROFIT_THRESHOLD = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.005"))  # 0.5%
    SLIPPAGE_TOLERANCE = float(os.getenv("SLIPPAGE_TOLERANCE", "0.02"))  # 2%
    EXECUTION_ENABLED = os.getenv("EXECUTION_ENABLED", "true").lower() == "true"

    # ── Circuit Breaker ──
    CIRCUIT_BREAKER_MAX_FAILURES = int(os.getenv("CIRCUIT_BREAKER_MAX_FAILURES", "3"))
    CIRCUIT_BREAKER_COOLDOWN_MIN = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_MIN", "15"))

    # ── Tokens to track ──
    TARGET_TOKENS = ["BNB", "CAKE", "BTCB", "ETH"]

    SEARCH_KEYWORDS = [
        "BNB price", "BNB pump", "BNB chain",
        "pancakeswap CAKE token",
        "BNB arbitrage", "pancakeswap arbitrage",
        "BNB listing", "BNB bullish"
    ]

    # ── Thresholds ──
    SENTIMENT_THRESHOLD    = 0.3
    PRICE_DIFF_THRESHOLD   = 0.005  # 0.5% — realistic for BSC
    POLL_INTERVAL_SECONDS  = 120    # 2 min — avoids rate limits