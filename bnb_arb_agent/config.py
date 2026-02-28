"""Agent configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from core.exceptions import ConfigurationError
from core.logger import get_logger

logger = get_logger(__name__)

# Walk up from this file's location to find the .env file, supporting both
# running from the project root and from within the bnb_arb_agent subdirectory.
_env_path = Path(__file__).parent
for _ in range(3):
    candidate = _env_path / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=False)
        break
    _env_path = _env_path.parent


def _require(key: str) -> str:
    value = os.getenv(key, "")
    if not value:
        raise ConfigurationError(f"Required environment variable '{key}' is not set.")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass
class Config:
    # Authentication
    google_api_key: str        = field(default_factory=lambda: _require("GOOGLE_API_KEY"))

    gnews_key: str             = field(default_factory=lambda: _optional("GNEWS_KEY"))
    thenewsapi_key: str        = field(default_factory=lambda: _optional("THENEWSAPI_KEY"))
    cryptopanic_key: str       = field(default_factory=lambda: _optional("CRYPTOPANIC_KEY"))
    newsapi_key: str           = field(default_factory=lambda: _optional("NEWSAPI_KEY"))
    twitter_bearer_token: str  = field(default_factory=lambda: _optional("TWITTER_BEARER_TOKEN"))
    bscscan_api_key: str       = field(default_factory=lambda: _optional("BSCSCAN_API_KEY"))
    github_token: str          = field(default_factory=lambda: _optional("GITHUB_TOKEN"))

    # Wallet
    private_key: str           = field(default_factory=lambda: _optional("PRIVATE_KEY"))
    wallet_address: str        = field(default_factory=lambda: _optional("WALLET_ADDRESS"))

    # MCP server
    mcp_server_url: str        = field(default_factory=lambda: _optional("MCP_SERVER_URL", "http://localhost:3001"))

    # Trade execution
    trade_amount_bnb: float    = field(default_factory=lambda: float(_optional("TRADE_AMOUNT_BNB", "0.01")))
    min_profit_threshold: float = field(default_factory=lambda: float(_optional("MIN_PROFIT_THRESHOLD", "0.005")))
    slippage_tolerance: float  = field(default_factory=lambda: float(_optional("SLIPPAGE_TOLERANCE", "0.02")))
    execution_enabled: bool    = field(default_factory=lambda: _optional("EXECUTION_ENABLED", "true").lower() == "true")

    # Circuit breaker
    circuit_breaker_max_failures: int  = field(default_factory=lambda: int(_optional("CIRCUIT_BREAKER_MAX_FAILURES", "3")))
    circuit_breaker_cooldown_min: int  = field(default_factory=lambda: int(_optional("CIRCUIT_BREAKER_COOLDOWN_MIN", "15")))

    # Agent behaviour
    target_tokens: list = field(default_factory=lambda: ["BNB", "CAKE", "BTCB", "ETH"])
    search_keywords: list = field(default_factory=lambda: [
        "BNB price", "BNB pump", "BNB chain",
        "pancakeswap CAKE token",
        "BNB arbitrage", "pancakeswap arbitrage",
        "BNB listing", "BNB bullish",
    ])
    sentiment_threshold: float   = 0.3
    price_diff_threshold: float  = 0.005
    poll_interval_seconds: int   = 120

    def __post_init__(self) -> None:
        """Warn on missing optional keys that degrade data quality."""
        optional_keys = {
            "gnews_key":        "GNEWS_KEY",
            "cryptopanic_key":  "CRYPTOPANIC_KEY",
            "bscscan_api_key":  "BSCSCAN_API_KEY",
        }
        for attr, env_key in optional_keys.items():
            if not getattr(self, attr):
                logger.warning("Optional key %s not set — related data source will be skipped.", env_key)