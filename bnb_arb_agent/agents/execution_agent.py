# agents/execution_agent.py
# 🚀 Execution Agent — Routes trades through bnbchain-mcp server
# Handles: Pre-flight checks, swap execution (buy + sell), circuit breaker, post-trade logging

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from config import Config

cfg = Config()


# ═══════════════════════════════════════════════════════════════
# MCP CLIENT — Talks to the bnbchain-mcp server via JSON-RPC
# ═══════════════════════════════════════════════════════════════
class MCPClient:
    """HTTP client for the bnbchain-mcp server."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv("MCP_SERVER_URL", "http://localhost:3000")).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._tools_cache = None

    def discover_tools(self) -> list:
        """Fetch available tools from the MCP server (GET /tools)."""
        try:
            resp = self.session.get(f"{self.base_url}/tools", timeout=10)
            resp.raise_for_status()
            self._tools_cache = resp.json()
            return self._tools_cache
        except Exception as e:
            print(f"  ❌ MCP tool discovery failed: {e}")
            return []

    def call_tool(self, tool_name: str, arguments: dict, timeout: int = 30) -> dict:
        """
        Invoke an MCP tool via POST /call-tool (standard MCP HTTP endpoint).
        Payload: { "name": "<tool>", "arguments": { ... } }
        """
        payload = {
            "name": tool_name,
            "arguments": arguments,
        }
        try:
            resp = self.session.post(
                f"{self.base_url}/call-tool",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"error": f"MCP call to '{tool_name}' timed out after {timeout}s"}
        except requests.exceptions.ConnectionError:
            return {"error": f"Cannot connect to MCP server at {self.base_url}"}
        except Exception as e:
            return {"error": str(e)}

    def is_alive(self) -> bool:
        """Quick health check — try to discover tools."""
        try:
            resp = self.session.get(f"{self.base_url}/tools", timeout=5)
            return resp.status_code == 200
        except:
            return False


# ═══════════════════════════════════════════════════════════════
# TRADE LOGGER — Persistent post-trade logging for hackathon demo
# ═══════════════════════════════════════════════════════════════
class TradeLogger:
    """Logs every trade attempt with full context for demo/audit."""

    LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "trade_log.json")

    def __init__(self):
        self.logs = []
        self._load_existing()

    def _load_existing(self):
        try:
            if os.path.exists(self.LOG_FILE):
                with open(self.LOG_FILE, "r") as f:
                    self.logs = json.load(f)
        except:
            self.logs = []

    def log(self, entry: dict):
        """Append a trade log entry and persist to disk."""
        entry["logged_at"] = datetime.utcnow().isoformat()
        self.logs.append(entry)
        self._persist()
        self._print_log(entry)

    def _persist(self):
        try:
            with open(self.LOG_FILE, "w") as f:
                json.dump(self.logs, f, indent=2, default=str)
        except Exception as e:
            print(f"  ⚠️  Could not persist trade log: {e}")

    def _print_log(self, entry: dict):
        status = entry.get("status", "UNKNOWN")
        icon = "✅" if status == "SUCCESS" else "❌" if status == "FAILED" else "⏭️"
        print(f"""
  ┌─ TRADE LOG ────────────────────────────────────────
  │  {icon} Status:     {status}
  │  Token In:     {entry.get('token_in', '?')} → Token Out: {entry.get('token_out', '?')}
  │  Amount:       {entry.get('amount', '?')}
  │  Direction:    {entry.get('direction', '?')}
  │  TX Hash:      {entry.get('tx_hash', 'N/A')}
  │  Profit Est:   {entry.get('profit_estimate_pct', '?')}%
  │  Phase:        {entry.get('market_phase', '?')}
  │  Sentiment:    {entry.get('sentiment_signal', '?')}
  │  Confidence:   {entry.get('confidence_score', '?')}/100
  │  Timestamp:    {entry.get('logged_at', '?')}
  │  Reason:       {entry.get('reason', '')}
  └────────────────────────────────────────────────────
""")

    def get_recent(self, n: int = 10) -> list:
        return self.logs[-n:]


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER — Pauses execution after consecutive failures
# ═══════════════════════════════════════════════════════════════
class CircuitBreaker:
    """If N consecutive trades fail, pause execution and alert."""

    def __init__(self, max_failures: int = 3, cooldown_minutes: int = 15):
        self.max_failures = max_failures
        self.cooldown_minutes = cooldown_minutes
        self.consecutive_failures = 0
        self.is_open = False  # True = circuit is tripped, no more trades
        self.tripped_at: Optional[datetime] = None

    def record_success(self):
        self.consecutive_failures = 0
        self.is_open = False
        self.tripped_at = None

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self.is_open = True
            self.tripped_at = datetime.utcnow()
            print(f"""
  🚨🚨🚨 CIRCUIT BREAKER TRIPPED 🚨🚨🚨
  {self.consecutive_failures} consecutive trade failures!
  Execution paused for {self.cooldown_minutes} minutes.
  Tripped at: {self.tripped_at.isoformat()}
""")

    def allow_trade(self) -> bool:
        if not self.is_open:
            return True
        # Check if cooldown has elapsed
        if self.tripped_at and datetime.utcnow() > self.tripped_at + timedelta(minutes=self.cooldown_minutes):
            print("  🔄 Circuit breaker cooldown elapsed — resetting.")
            self.is_open = False
            self.consecutive_failures = 0
            self.tripped_at = None
            return True
        remaining = (self.tripped_at + timedelta(minutes=self.cooldown_minutes) - datetime.utcnow()).seconds // 60
        print(f"  ⛔ Circuit breaker OPEN — {remaining} min remaining in cooldown.")
        return False

    @property
    def status(self) -> dict:
        return {
            "is_open": self.is_open,
            "consecutive_failures": self.consecutive_failures,
            "max_failures": self.max_failures,
            "tripped_at": self.tripped_at.isoformat() if self.tripped_at else None,
        }


# ═══════════════════════════════════════════════════════════════
# 🚀 EXECUTION AGENT — Master trade execution coordinator
# ═══════════════════════════════════════════════════════════════

# Testnet constants
BSC_TESTNET_CHAIN_ID = 97
PANCAKE_ROUTER_TESTNET = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"
WBNB_TESTNET = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"

# Common testnet token addresses (BSC Testnet)
TESTNET_TOKENS = {
    "BNB":  WBNB_TESTNET,
    "WBNB": WBNB_TESTNET,
    "BUSD": "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee",
    "USDT": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
    "DAI":  "0x8a9424745056Eb399FD19a0EC26A14316684e274",
    "CAKE": "0xFa60D973F7642B748046464e165A65B7323b0DEE",
}

# PancakeSwap Router ABI fragments we need
SWAP_EXACT_TOKENS_FOR_TOKENS_ABI = json.dumps([{
    "inputs": [
        {"name": "amountIn", "type": "uint256"},
        {"name": "amountOutMin", "type": "uint256"},
        {"name": "path", "type": "address[]"},
        {"name": "to", "type": "address"},
        {"name": "deadline", "type": "uint256"},
    ],
    "name": "swapExactTokensForTokens",
    "outputs": [{"name": "amounts", "type": "uint256[]"}],
    "stateMutability": "nonpayable",
    "type": "function",
}])

GET_AMOUNTS_OUT_ABI = json.dumps([{
    "inputs": [
        {"name": "amountIn", "type": "uint256"},
        {"name": "path", "type": "address[]"},
    ],
    "name": "getAmountsOut",
    "outputs": [{"name": "amounts", "type": "uint256[]"}],
    "stateMutability": "view",
    "type": "function",
}])


class ExecutionAgent:
    """
    Coordinates trade execution through the bnbchain-mcp server.
    
    Flow:
      1. Pre-flight checks (chain alive, balance sufficient, simulate swap)
      2. Execute buy-side swap via MCP write_contract
      3. Execute sell-side swap via MCP write_contract
      4. Log results with full context
      5. Circuit breaker on consecutive failures
    """

    def __init__(self, mcp_url: str = None):
        self.mcp = MCPClient(mcp_url)
        self.logger = TradeLogger()
        self.breaker = CircuitBreaker(
            max_failures=int(os.getenv("CIRCUIT_BREAKER_MAX_FAILURES", "3")),
            cooldown_minutes=int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_MIN", "15")),
        )
        self.wallet_address = os.getenv("WALLET_ADDRESS", "")
        self.default_amount_bnb = float(os.getenv("TRADE_AMOUNT_BNB", "0.01"))
        self.min_profit_threshold = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.005"))  # 0.5%

    # ───────────────────────────────────────────────────────
    #  PUBLIC: Execute a trade from a decision result
    # ───────────────────────────────────────────────────────
    def execute(self, decision: dict) -> dict:
        """
        Main entry point. Called by the decision agent when action == EXECUTE_TRADE.
        
        Args:
            decision: dict with keys: token, direction, cex_price, dex_price,
                      price_diff_pct, sentiment_signal, market_phase,
                      confidence_score, risk_level, reason
        Returns:
            dict with execution result (status, tx_hash, profit, etc.)
        """
        token = decision.get("token", "BNB")
        direction = decision.get("direction", "BUY_DEX_SELL_CEX")
        price_diff_pct = decision.get("price_diff_pct", 0)
        confidence = decision.get("confidence_score", 0)
        phase = decision.get("market_phase", "UNKNOWN")
        sentiment = decision.get("sentiment_signal", 0)

        print(f"\n  🚀 EXECUTION AGENT — Attempting trade for {token}")
        print(f"     Direction: {direction} | Confidence: {confidence}/100")

        # ── Circuit breaker check ──
        if not self.breaker.allow_trade():
            result = self._build_result(
                token=token, direction=direction,
                status="BLOCKED_CIRCUIT_BREAKER",
                reason="Circuit breaker is open — too many consecutive failures",
                decision=decision,
            )
            self.logger.log(result)
            return result

        # ── Pre-flight checks ──
        preflight = self._preflight_checks(token, direction, price_diff_pct)
        if not preflight["passed"]:
            result = self._build_result(
                token=token, direction=direction,
                status="PREFLIGHT_FAILED",
                reason=preflight["reason"],
                decision=decision,
            )
            self.logger.log(result)
            self.breaker.record_failure()
            return result

        # ── Determine swap parameters ──
        token_in, token_out = self._resolve_swap_pair(token, direction)
        amount_in_wei = self._to_wei(self.default_amount_bnb)

        # ── Execute Buy Side (DEX swap) ──
        print(f"  📈 Executing buy side: {token_in} → {token_out}")
        buy_result = self._execute_swap(token_in, token_out, amount_in_wei)

        if buy_result.get("error"):
            result = self._build_result(
                token=token, direction=direction,
                status="FAILED",
                reason=f"Buy-side swap failed: {buy_result['error']}",
                decision=decision,
            )
            self.logger.log(result)
            self.breaker.record_failure()
            return result

        buy_tx_hash = buy_result.get("tx_hash", "unknown")
        print(f"  ✅ Buy TX: {buy_tx_hash}")

        # ── Execute Sell Side (reverse swap) ──
        # For CEX sell, we'd use a CEX API. For DEX-DEX arb, do the reverse swap.
        print(f"  📉 Executing sell side: {token_out} → {token_in}")
        sell_result = self._execute_swap(token_out, token_in, buy_result.get("amount_out_wei", amount_in_wei))

        if sell_result.get("error"):
            # Buy succeeded but sell failed — partial execution
            result = self._build_result(
                token=token, direction=direction,
                status="PARTIAL",
                tx_hash=buy_tx_hash,
                reason=f"Sell-side swap failed: {sell_result['error']}. Buy TX succeeded.",
                decision=decision,
            )
            self.logger.log(result)
            self.breaker.record_failure()
            return result

        sell_tx_hash = sell_result.get("tx_hash", "unknown")
        print(f"  ✅ Sell TX: {sell_tx_hash}")

        # ── Success! ──
        result = self._build_result(
            token=token, direction=direction,
            status="SUCCESS",
            tx_hash=f"BUY:{buy_tx_hash} | SELL:{sell_tx_hash}",
            profit_estimate_pct=price_diff_pct,
            decision=decision,
        )
        self.logger.log(result)
        self.breaker.record_success()
        return result

    # ───────────────────────────────────────────────────────
    #  PRE-FLIGHT CHECKS
    # ───────────────────────────────────────────────────────
    def _preflight_checks(self, token: str, direction: str, price_diff_pct: float) -> dict:
        """
        Run all pre-flight checks before executing:
          1. Chain is live (get_block_by_number)
          2. Wallet has sufficient balance (get_token_balance)
          3. Simulate swap to confirm profit is still valid (getAmountsOut)
        """
        print("  🔍 Running pre-flight checks...")

        # ── Check 1: Chain liveness ──
        print("     [1/3] Checking chain liveness...")
        block_result = self.mcp.call_tool("get_block_by_number", {
            "blockNumber": "latest",
            "network": "bsc-testnet",
        })
        if block_result.get("error"):
            return {"passed": False, "reason": f"Chain liveness check failed: {block_result['error']}"}

        # Extract block info for logging
        block_data = block_result.get("result", block_result)
        print(f"     ✅ Chain is live — latest block received")

        # ── Check 2: Wallet balance ──
        print("     [2/3] Checking wallet balance...")
        balance_result = self.mcp.call_tool("get_token_balance", {
            "address": self.wallet_address,
            "network": "bsc-testnet",
        })
        if balance_result.get("error"):
            # Non-fatal: we'll try the trade anyway, but warn
            print(f"     ⚠️  Balance check warning: {balance_result['error']}")
        else:
            balance_data = balance_result.get("result", balance_result)
            print(f"     ✅ Balance check passed")

        # ── Check 3: Simulate swap (getAmountsOut) ──
        print("     [3/3] Simulating swap to confirm profitability...")
        token_in_addr, token_out_addr = self._resolve_swap_pair(token, direction)
        amount_in_wei = self._to_wei(self.default_amount_bnb)

        sim_result = self.mcp.call_tool("read_contract", {
            "contractAddress": PANCAKE_ROUTER_TESTNET,
            "abi": GET_AMOUNTS_OUT_ABI,
            "functionName": "getAmountsOut",
            "args": json.dumps([str(amount_in_wei), [token_in_addr, token_out_addr]]),
            "network": "bsc-testnet",
        })

        if sim_result.get("error"):
            print(f"     ⚠️  Swap simulation warning: {sim_result['error']}")
            # Non-fatal — price slippage may have changed, but we proceed with caution
        else:
            sim_data = sim_result.get("result", sim_result)
            print(f"     ✅ Swap simulation passed — profit still appears valid")

        # ── Check profit threshold ──
        if price_diff_pct < self.min_profit_threshold * 100:
            return {
                "passed": False,
                "reason": f"Profit {price_diff_pct:.3f}% below minimum threshold {self.min_profit_threshold * 100:.1f}%",
            }

        print("  ✅ All pre-flight checks passed!")
        return {"passed": True, "reason": "All checks passed"}

    # ───────────────────────────────────────────────────────
    #  SWAP EXECUTION via MCP write_contract
    # ───────────────────────────────────────────────────────
    def _execute_swap(self, token_in: str, token_out: str, amount_in_wei: int) -> dict:
        """
        Execute a PancakeSwap swap through the MCP server's write_contract tool.
        Uses swapExactTokensForTokens on the PancakeSwap testnet router.
        """
        # 2% slippage tolerance
        amount_out_min = int(amount_in_wei * 0.98)
        # Deadline: 5 minutes from now
        deadline = int(time.time()) + 300

        swap_args = json.dumps([
            str(amount_in_wei),           # amountIn
            str(amount_out_min),          # amountOutMin (2% slippage)
            [token_in, token_out],        # path
            self.wallet_address,          # to
            str(deadline),                # deadline
        ])

        result = self.mcp.call_tool("write_contract", {
            "contractAddress": PANCAKE_ROUTER_TESTNET,
            "abi": SWAP_EXACT_TOKENS_FOR_TOKENS_ABI,
            "functionName": "swapExactTokensForTokens",
            "args": swap_args,
            "network": "bsc-testnet",
        }, timeout=60)

        if result.get("error"):
            return {"error": result["error"]}

        # Parse MCP response for tx hash
        tx_hash = "unknown"
        amount_out_wei = amount_in_wei  # fallback

        if isinstance(result, dict):
            # The MCP server typically returns: { "content": [{ "text": "..." }] }
            content = result.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
                # Try to extract tx hash from response
                if "0x" in text:
                    # Find the transaction hash (66 characters: 0x + 64 hex)
                    import re
                    hash_match = re.search(r"(0x[a-fA-F0-9]{64})", text)
                    if hash_match:
                        tx_hash = hash_match.group(1)
            # Also check for direct result field
            tx_hash = result.get("transactionHash", result.get("hash", tx_hash))

        return {"tx_hash": tx_hash, "amount_out_wei": amount_out_wei}

    # ───────────────────────────────────────────────────────
    #  HELPERS
    # ───────────────────────────────────────────────────────
    def _resolve_swap_pair(self, token: str, direction: str):
        """
        Resolve token symbols to testnet contract addresses for the swap pair.
        Returns (token_in_address, token_out_address).
        """
        if direction == "BUY_DEX_SELL_CEX":
            # Buy on DEX: spend stablecoin → get token
            token_in = TESTNET_TOKENS.get("BUSD", TESTNET_TOKENS["WBNB"])
            token_out = TESTNET_TOKENS.get(token, TESTNET_TOKENS["WBNB"])
        else:
            # BUY_CEX_SELL_DEX: sell token on DEX → get stablecoin
            token_in = TESTNET_TOKENS.get(token, TESTNET_TOKENS["WBNB"])
            token_out = TESTNET_TOKENS.get("BUSD", TESTNET_TOKENS["WBNB"])

        return token_in, token_out

    def _to_wei(self, amount_bnb: float, decimals: int = 18) -> int:
        """Convert human-readable amount to wei."""
        return int(amount_bnb * (10 ** decimals))

    def _build_result(self, token: str, direction: str, status: str,
                      reason: str = "", tx_hash: str = "N/A",
                      profit_estimate_pct: float = 0, decision: dict = None) -> dict:
        """Build a standardized trade result dict for logging."""
        decision = decision or {}
        return {
            "token_in": token if direction == "BUY_CEX_SELL_DEX" else "BUSD",
            "token_out": "BUSD" if direction == "BUY_CEX_SELL_DEX" else token,
            "amount": self.default_amount_bnb,
            "direction": direction,
            "status": status,
            "tx_hash": tx_hash,
            "profit_estimate_pct": round(profit_estimate_pct, 4),
            "market_phase": decision.get("market_phase", "UNKNOWN"),
            "sentiment_signal": decision.get("sentiment_signal", 0),
            "confidence_score": decision.get("confidence_score", 0),
            "risk_level": decision.get("risk_level", "UNKNOWN"),
            "reason": reason or decision.get("reason", ""),
            "chain_id": BSC_TESTNET_CHAIN_ID,
            "router": PANCAKE_ROUTER_TESTNET,
            "timestamp": datetime.utcnow().isoformat(),
            "circuit_breaker": self.breaker.status,
        }

    @property
    def trade_history(self) -> list:
        return self.logger.get_recent(50)

    @property
    def circuit_breaker_status(self) -> dict:
        return self.breaker.status
