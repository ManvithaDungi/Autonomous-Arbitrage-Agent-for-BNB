"""Trade execution agent — routes swap orders through the bnbchain-mcp server."""

import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

import requests

from core.constants import (
    BSC_TESTNET_CHAIN_ID,
    PANCAKE_V2_ROUTER_TESTNET,
    SWAP_ABI_JSON,
    ROUTER_ABI_JSON,
    TESTNET_TOKENS,
)
from core.exceptions import MCPError
from core.logger import get_logger

logger = get_logger(__name__)

_TX_HASH_PATTERN = re.compile(r"(0x[a-fA-F0-9]{64})")


class MCPClient:
    """Async MCP client over SSE transport.

    Each call opens a new SSE session. This avoids shared-state issues when
    the client is used from synchronous contexts via asyncio.run().
    """

    def __init__(self, base_url: str) -> None:
        self._sse_url = base_url.rstrip("/") + "/sse"

    def is_alive(self) -> bool:
        try:
            response = requests.get(self._sse_url, timeout=5, stream=True)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Invoke an MCP tool and return the response dict."""
        return asyncio.run(self._call_tool_async(tool_name, arguments))

    async def _call_tool_async(self, tool_name: str, arguments: dict) -> dict:
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            async with sse_client(self._sse_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    content = result.content
                    if content and hasattr(content[0], "text"):
                        return {"result": content[0].text, "content": [c.model_dump() for c in content]}
                    return {"result": str(content)}
        except Exception as exc:
            return {"error": str(exc)}


class CircuitBreaker:
    """Pauses trade execution after a configurable number of consecutive failures."""

    def __init__(self, max_failures: int = 3, cooldown_minutes: int = 15) -> None:
        self._max_failures      = max_failures
        self._cooldown          = timedelta(minutes=cooldown_minutes)
        self._failures          = 0
        self._is_open           = False
        self._tripped_at: Optional[datetime] = None

    def record_success(self) -> None:
        self._failures  = 0
        self._is_open   = False
        self._tripped_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._max_failures:
            self._is_open   = True
            self._tripped_at = datetime.utcnow()
            logger.error("Circuit breaker tripped after %d failures.", self._failures)

    def allow_trade(self) -> bool:
        if not self._is_open:
            return True
        if self._tripped_at and datetime.utcnow() > self._tripped_at + self._cooldown:
            logger.info("Circuit breaker cooldown elapsed — resetting.")
            self._is_open    = False
            self._failures   = 0
            self._tripped_at = None
            return True
        remaining = int((self._tripped_at + self._cooldown - datetime.utcnow()).seconds / 60)
        logger.warning("Circuit breaker open — %d min remaining in cooldown.", remaining)
        return False

    @property
    def status(self) -> dict:
        return {
            "is_open":            self._is_open,
            "consecutive_failures": self._failures,
            "tripped_at":         self._tripped_at.isoformat() if self._tripped_at else None,
        }


class TradeLogger:
    """Persists trade attempts to a JSON file for audit and hackathon demo purposes."""

    _LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "trade_log.json")

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._LOG_FILE):
                with open(self._LOG_FILE) as fh:
                    self._records = json.load(fh)
        except (OSError, json.JSONDecodeError):
            self._records = []

    def log(self, entry: dict) -> None:
        entry["logged_at"] = datetime.utcnow().isoformat()
        self._records.append(entry)
        try:
            with open(self._LOG_FILE, "w") as fh:
                json.dump(self._records, fh, indent=2, default=str)
        except OSError:
            logger.warning("Could not persist trade log.")
        logger.info(
            "Trade logged: %s | status=%s | tx=%s",
            entry.get("direction"),
            entry.get("status"),
            entry.get("tx_hash", "N/A"),
        )

    def recent(self, count: int = 10) -> list[dict]:
        return self._records[-count:]


class ExecutionAgent:
    """Executes arbitrage swaps on BSC Testnet via the bnbchain-mcp server.

    Flow:
        1. Circuit breaker check
        2. Pre-flight (chain liveness, balance, swap simulation)
        3. Buy-side swap (spend stablecoin, acquire token)
        4. Sell-side swap (dispose of token)
        5. log result
    """

    def __init__(self, mcp_url: str = None) -> None:
        url = mcp_url or os.getenv("MCP_SERVER_URL", "http://localhost:3001")
        self._mcp            = MCPClient(url)
        self._logger         = TradeLogger()
        self._breaker        = CircuitBreaker(
            max_failures    = int(os.getenv("CIRCUIT_BREAKER_MAX_FAILURES", "3")),
            cooldown_minutes = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_MIN", "15")),
        )
        self._wallet         = os.getenv("WALLET_ADDRESS", "")
        self._amount_bnb     = float(os.getenv("TRADE_AMOUNT_BNB", "0.01"))
        self._min_profit     = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.005"))

    def execute(self, decision: dict) -> dict:
        """Execute a trade based on *decision*, returning a result dict."""
        token      = decision.get("token", "BNB")
        direction  = decision.get("direction", "BUY_DEX_SELL_CEX")
        price_diff = decision.get("price_diff_pct", 0.0)

        if not self._breaker.allow_trade():
            return self._build_result(token, direction, "BLOCKED_CIRCUIT_BREAKER",
                                      "Circuit breaker is open.", decision)

        preflight = self._preflight(token, direction, price_diff)
        if not preflight["passed"]:
            result = self._build_result(token, direction, "PREFLIGHT_FAILED", preflight["reason"], decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        token_in, token_out = self._swap_pair(token, direction)
        amount_wei          = self._to_wei(self._amount_bnb)

        buy = self._swap(token_in, token_out, amount_wei)
        if buy.get("error"):
            result = self._build_result(token, direction, "FAILED",
                                        f"Buy-side failed: {buy['error']}", decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        sell = self._swap(token_out, token_in, buy.get("amount_out_wei", amount_wei))
        if sell.get("error"):
            result = self._build_result(token, direction, "PARTIAL",
                                        f"Sell-side failed: {sell['error']}",
                                        decision, tx_hash=buy.get("tx_hash"))
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        result = self._build_result(
            token, direction, "SUCCESS", "",
            decision,
            tx_hash=f"BUY:{buy['tx_hash']} SELL:{sell['tx_hash']}",
            profit_pct=price_diff,
        )
        self._logger.log(result)
        self._breaker.record_success()
        return result

    def _preflight(self, token: str, direction: str, price_diff: float) -> dict:
        block = self._mcp.call_tool("get_block_by_number", {"blockNumber": "latest", "network": "bsc-testnet"})
        if block.get("error"):
            return {"passed": False, "reason": f"Chain check failed: {block['error']}"}

        self._mcp.call_tool("get_token_balance", {"address": self._wallet, "network": "bsc-testnet"})

        token_in, token_out = self._swap_pair(token, direction)
        self._mcp.call_tool("read_contract", {
            "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
            "abi":             ROUTER_ABI_JSON,
            "functionName":    "getAmountsOut",
            "args":            json.dumps([str(self._to_wei(self._amount_bnb)), [token_in, token_out]]),
            "network":         "bsc-testnet",
        })

        if price_diff < self._min_profit * 100:
            return {"passed": False, "reason": f"Profit {price_diff:.3f}% below minimum {self._min_profit * 100:.1f}%"}

        return {"passed": True, "reason": ""}

    def _swap(self, token_in: str, token_out: str, amount_wei: int) -> dict:
        args = json.dumps([
            str(amount_wei),
            str(int(amount_wei * 0.98)),  # 2% slippage
            [token_in, token_out],
            self._wallet,
            str(int(time.time()) + 300),  # 5-minute deadline
        ])
        result = self._mcp.call_tool("write_contract", {
            "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
            "abi":             SWAP_ABI_JSON,
            "functionName":    "swapExactTokensForTokens",
            "args":            args,
            "network":         "bsc-testnet",
        })
        if result.get("error"):
            return {"error": result["error"]}

        tx_hash = result.get("transactionHash", result.get("hash", "unknown"))
        content = result.get("content", [])
        if not tx_hash or tx_hash == "unknown":
            for item in content:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                match = _TX_HASH_PATTERN.search(text)
                if match:
                    tx_hash = match.group(1)
                    break

        return {"tx_hash": tx_hash, "amount_out_wei": amount_wei}

    def _swap_pair(self, token: str, direction: str) -> tuple[str, str]:
        stable = TESTNET_TOKENS.get("BUSD", TESTNET_TOKENS["BNB"])
        token_addr = TESTNET_TOKENS.get(token, TESTNET_TOKENS["BNB"])
        if direction == "BUY_DEX_SELL_CEX":
            return stable, token_addr
        return token_addr, stable

    @staticmethod
    def _to_wei(amount: float, decimals: int = 18) -> int:
        return int(amount * (10 ** decimals))

    def _build_result(
        self,
        token:      str,
        direction:  str,
        status:     str,
        reason:     str,
        decision:   dict,
        tx_hash:    str = "N/A",
        profit_pct: float = 0.0,
    ) -> dict:
        return {
            "token_in":             token if direction == "BUY_CEX_SELL_DEX" else "BUSD",
            "token_out":            "BUSD" if direction == "BUY_CEX_SELL_DEX" else token,
            "amount":               self._amount_bnb,
            "direction":            direction,
            "status":               status,
            "tx_hash":              tx_hash,
            "profit_estimate_pct":  round(profit_pct, 4),
            "market_phase":         decision.get("market_phase", "UNKNOWN"),
            "sentiment_signal":     decision.get("sentiment_signal", 0.0),
            "confidence_score":     decision.get("confidence_score", 0),
            "risk_level":           decision.get("risk_level", "UNKNOWN"),
            "reason":               reason or decision.get("reason", ""),
            "chain_id":             BSC_TESTNET_CHAIN_ID,
            "router":               PANCAKE_V2_ROUTER_TESTNET,
            "timestamp":            datetime.utcnow().isoformat(),
            "circuit_breaker":      self._breaker.status,
        }

    @property
    def trade_history(self) -> list[dict]:
        return self._logger.recent(50)

    @property
    def circuit_breaker_status(self) -> dict:
        return self._breaker.status
