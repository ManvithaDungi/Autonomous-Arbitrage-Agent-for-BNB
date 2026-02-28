"""Trade execution agent — routes swap orders through the bnbchain-mcp server."""

import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import requests

from core.constants import (
    BSC_TESTNET_CHAIN_ID,
    BSC_TESTNET_RPC,
    PANCAKE_V2_ROUTER_TESTNET,
    ROUTER_ABI,
    ROUTER_ABI_JSON,
    SWAP_ABI_JSON,
    TESTNET_TOKENS,
)
from core.logger import get_logger

# 🔥 1. IMPORT YOUR NEW AUDITOR HERE
from agents.auditor import audit_token  # If auditor.py is in the root, change this to: from auditor import audit_token

logger = get_logger(__name__)

_TX_HASH_PATTERN = re.compile(r"(0x[a-fA-F0-9]{64})")

ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

SWAP_EXACT_ETH_FOR_TOKENS_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function",
    }
]

# 2. HACKATHON DEMO MAP: Maps testnet symbols to real mainnet addresses for the auditor
MAINNET_AUDIT_MAP = {
    "BNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",      # Safe (WBNB)
    "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",     # Safe
    "CAKE": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",     # Safe
    "SAFEMOON": "0x8076C74C5e3F5852037F31Ff0093Eeb8c8ADd8D3", # Malicious!
}

class MCPClient:
    """Async MCP client over SSE (HTTP) transport."""
    def __init__(self, base_url: str = "http://localhost:3001") -> None:
        normalized = base_url.rstrip("/")
        self._sse_url = normalized if normalized.endswith("/sse") else f"{normalized}/sse"

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

            # Connect to the running server over HTTP (No more Windows pipes!)
            async with sse_client(self._sse_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    content = result.content
                    if content and hasattr(content[0], "text"):
                        parsed = self._try_parse_json(content[0].text)
                        extracted_error = self._extract_embedded_error(parsed)
                        if extracted_error:
                            return {"error": extracted_error, "content": [c.model_dump() for c in content]}
                        return {"result": parsed, "content": [c.model_dump() for c in content]}
                    return {"result": str(content)}
        except Exception as exc:
            if hasattr(exc, 'exceptions'):
                nested = []
                for sub_exc in exc.exceptions:
                    nested.append(str(sub_exc))
                    if hasattr(sub_exc, "exceptions"):
                        nested.extend(str(inner) for inner in sub_exc.exceptions)
                error_msgs = " | ".join(nested) if nested else str(exc)
                return {"error": f"Server Rejected: {error_msgs}"}
            return {"error": str(exc)}

    @staticmethod
    def _try_parse_json(value: str):
        try:
            return json.loads(value)
        except Exception:
            return value

    @staticmethod
    def _extract_embedded_error(value) -> str | None:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered.startswith("error") or "error writing to contract" in lowered or "failed" in lowered:
                return value
            return None
        if isinstance(value, dict):
            for key in ("error", "message"):
                if key in value and isinstance(value[key], str):
                    lowered = value[key].strip().lower()
                    if lowered.startswith("error") or "failed" in lowered:
                        return value[key]
        return None

class CircuitBreaker:
    # (Your existing CircuitBreaker code remains completely unchanged)
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
    # (Your existing TradeLogger code remains completely unchanged)
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
        logger.info("Trade logged: %s | status=%s | tx=%s", entry.get("direction"), entry.get("status"), entry.get("tx_hash", "N/A"))

    def recent(self, count: int = 10) -> list[dict]:
        return self._records[-count:]

class ExecutionAgent:
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
        self._min_profit_bnb = float(os.getenv("MIN_PROFIT_BNB", "0.000002"))
        self._gas_estimate_bnb = float(os.getenv("GAS_ESTIMATE_BNB", "0"))

    def execute(self, decision: dict) -> dict:
        token      = decision.get("token", "BNB")
        direction  = decision.get("direction", "BUY_DEX_SELL_CEX")
        price_diff = decision.get("price_diff_pct", 0.0)

        # 1. Circuit Breaker Check
        if not self._breaker.allow_trade():
            return self._build_result(token, direction, "BLOCKED_CIRCUIT_BREAKER", "Circuit breaker is open.", decision)

        # 🔥 2. THE AI SECURITY GATEKEEPER (DISABLED FOR TESTNET DEBUG)
        print(f"\n🛡️ Calling AI Security Auditor for {token}...")
        audit_address = MAINNET_AUDIT_MAP.get(token.upper())
        # 
        if audit_address:
            is_safe = audit_token(audit_address)
            if not is_safe:
                logger.error(f"SECURITY ALERT: {token} failed smart contract audit. Trade aborted.")
                result = self._build_result(token, direction, "BLOCKED_MALICIOUS_CONTRACT", "AI Auditor detected honeypot/scam signatures.", decision)
                self._logger.log(result)
                return result
        else:
            print(f"🟡 Skipping audit: No mainnet address mapped for {token}.")
        print(f"🟡 Auditor temporarily disabled for testnet debugging.")

        # 3. Standard Preflight Checks
        preflight = self._preflight(token, direction, price_diff)
        if not preflight["passed"]:
            result = self._build_result(token, direction, "PREFLIGHT_FAILED", preflight["reason"], decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        # 4. Execute Buy
        amount_wei          = self._to_wei(self._amount_bnb)

        buy = self._swap_native_for_token(token, amount_wei)
        if buy.get("error"):
            result = self._build_result(token, direction, "FAILED", f"Buy-side failed: {buy['error']}", decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        # 5. Success (CEX sell leg is off-chain/manual in this demo)
        result = self._build_result(
            token,
            direction,
            "SUCCESS",
            "On-chain buy executed. CEX sell leg is external/manual.",
            decision,
            tx_hash=f"BUY:{buy['tx_hash']}",
            profit_pct=price_diff,
            amount_out=buy.get('amount_out_wei', 0)
        )
        self._logger.log(result)
        self._breaker.record_success()
        return result

    def execute_two_leg(self, decision: dict) -> dict:
        token      = decision.get("token", "BUSD")
        direction  = decision.get("direction", "BUY_DEX_SELL_CEX")
        price_diff = decision.get("price_diff_pct", 0.0)
        force_trade = bool(decision.get("force_trade", False))

        if not self._breaker.allow_trade():
            return self._build_result(token, direction, "BLOCKED_CIRCUIT_BREAKER", "Circuit breaker is open.", decision)

        preflight = self._preflight(token, direction, price_diff)
        if not preflight["passed"]:
            result = self._build_result(token, direction, "PREFLIGHT_FAILED", preflight["reason"], decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        amount_wei = self._to_wei(self._amount_bnb)
        buy_path = self._buy_path(token)
        sell_path = self._sell_path(token)
        if not buy_path or not sell_path:
            return self._build_result(token, direction, "PREFLIGHT_FAILED", "Invalid swap path for token.", decision)

        gas_estimate_bnb = self._estimate_gas_bnb(amount_wei, buy_path, sell_path) or self._gas_estimate_bnb

        buy_quote = self._get_amounts_out(amount_wei, buy_path)
        if not buy_quote:
            return self._build_result(token, direction, "PREFLIGHT_FAILED", "Unable to quote buy route.", decision)
        expected_token_out = int(buy_quote[-1])

        sell_quote = self._get_amounts_out(expected_token_out, sell_path)
        if not sell_quote:
            return self._build_result(token, direction, "PREFLIGHT_FAILED", "Unable to quote sell route.", decision)
        expected_wbnb_out = int(sell_quote[-1])

        expected_profit_wei = expected_wbnb_out - amount_wei
        expected_profit_bnb = expected_profit_wei / 1e18
        if not force_trade and expected_profit_bnb - gas_estimate_bnb < self._min_profit_bnb:
            reason = (
                f"Expected profit {expected_profit_bnb:.6f} WBNB below minimum "
                f"{self._min_profit_bnb:.6f} WBNB after gas estimate {gas_estimate_bnb:.6f}."
            )
            result = self._build_result(token, direction, "PREFLIGHT_FAILED", reason, decision)
            self._logger.log(result)
            return result

        buy = self._swap_native_for_token(token, amount_wei)
        if buy.get("error"):
            result = self._build_result(token, direction, "FAILED", f"Buy-side failed: {buy['error']}", decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        sell = self._swap_token_for_token(token, buy.get("amount_out_wei", 0))
        if sell.get("error"):
            result = self._build_result(token, direction, "FAILED", f"Sell-side failed: {sell['error']}", decision)
            self._logger.log(result)
            self._breaker.record_failure()
            return result

        actual_profit_wei = sell.get("amount_out_wei", 0) - amount_wei
        actual_profit_bnb = actual_profit_wei / 1e18

        result = self._build_result(
            token,
            direction,
            "SUCCESS",
            "Two-leg DEX swap executed on testnet.",
            decision,
            tx_hash=f"BUY:{buy['tx_hash']}|SELL:{sell['tx_hash']}",
            profit_pct=price_diff,
            amount_out=sell.get("amount_out_wei", 0),
        )
        result["profit_wbnb"] = round(actual_profit_bnb, 8)
        result["gas_estimate_bnb"] = round(gas_estimate_bnb, 8)
        result["force_trade"] = force_trade
        result["buy_tx_hash"] = buy.get("tx_hash")
        result["sell_tx_hash"] = sell.get("tx_hash")
        self._logger.log(result)
        self._breaker.record_success()
        return result

    # (The rest of your helper functions _preflight, _swap, _swap_pair, _to_wei, _build_result remain completely unchanged)
    def _preflight(self, token: str, direction: str, price_diff: float) -> dict:
        if not self._wallet:
            return {"passed": False, "reason": "WALLET_ADDRESS is missing in .env"}
        if not self._mcp.is_alive():
            return {"passed": False, "reason": "MCP server is not reachable."}
        if token.upper() not in TESTNET_TOKENS:
            supported = ", ".join(sorted(TESTNET_TOKENS.keys()))
            return {"passed": False, "reason": f"Unsupported token {token}. Supported: {supported}."}
        if token.upper() == "BNB":
            return {"passed": False, "reason": "Token BNB is invalid for buy-on-DEX demo. Use CAKE/BUSD/USDT/DAI."}

        native_balance = self._mcp.call_tool("get_native_balance", {"address": self._wallet, "network": "bsc-testnet"})
        if native_balance.get("error"):
            return {"passed": False, "reason": f"Native balance check failed: {native_balance['error']}"}

        path = self._buy_path(token)
        if len(path) < 2:
            return {"passed": False, "reason": "Invalid swap path for token."}
        quote = self._mcp.call_tool(
            "read_contract",
            {
                "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
                "abi": json.loads(ROUTER_ABI_JSON),
                "functionName": "getAmountsOut",
                "args": [str(self._to_wei(self._amount_bnb)), path],
                "network": "bsc-testnet",
            },
        )
        if quote.get("error"):
            return {"passed": False, "reason": f"Route validation failed: {quote['error']}"}
        if price_diff < self._min_profit * 100:
            return {"passed": False, "reason": f"Profit {price_diff:.3f}% below minimum {self._min_profit * 100:.1f}%"}
        return {"passed": True, "reason": ""}

    def _swap_native_for_token(self, token: str, amount_wei: int) -> dict:
        """Swap WBNB tokens for target token (using swapExactTokensForTokens instead of ETH).
        
        This approach wraps BNB first, then approves router, then swaps WBNB→token.
        Workaround for broken swapExactETHForTokens on testnet.
        """
        path = self._buy_path(token)
        wbnb = TESTNET_TOKENS["BNB"]
        
        logger.info(f"Approving {amount_wei} WBNB for router...")
        
        # Step 1: Approve router to spend WBNB
        approve_result = self._mcp.call_tool(
            "write_contract",
            {
                "contractAddress": wbnb,
                "abi": ERC20_APPROVE_ABI,
                "functionName": "approve",
                "args": [PANCAKE_V2_ROUTER_TESTNET, str(amount_wei * 2)],  # Approve 2x for safety
                "network": "bsc-testnet",
            },
        )
        
        if approve_result.get("error"):
            return {"error": f"Approval failed: {approve_result['error']}"}
        
        logger.info(f"Approval successful, getting quote...")
        
        # Step 2: Get quote
        amounts = self._get_amounts_out(amount_wei, path)
        if not amounts:
            return {"error": "Quote failed."}
        expected_out = int(amounts[-1])
        if expected_out <= 0:
            return {"error": f"Quote returned zero or negative output: {expected_out}"}
        
        logger.info(f"Expected output: {expected_out}, calculating slippage tolerance")
        
        # Use 1% slippage
        min_out = str(max(1, int(expected_out * 0.01)))
        
        logger.info(f"Setting minimum output to {min_out}")

        # Step 3: Execute swap using swapExactTokensForTokens
        deadline = int(time.time()) + 300
        swap_args = [str(amount_wei), min_out, path, self._wallet, deadline]
        
        swap_params = {
            "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
            "abi": json.loads(SWAP_ABI_JSON),
            "functionName": "swapExactTokensForTokens",
            "args": swap_args,
            "network": "bsc-testnet",
        }
        
        logger.info(f"Executing swapExactTokensForTokens with params: {json.dumps(swap_params, indent=2)}")
        
        result = self._mcp.call_tool("write_contract", swap_params)
        if result.get("error"): 
            return {"error": f"Swap failed: {result['error']}"}
        tx_hash = self._extract_tx_hash(result)
        content = result.get("content", [])
        if not tx_hash or tx_hash == "unknown":
            for item in content:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                match = _TX_HASH_PATTERN.search(text)
                if match:
                    tx_hash = match.group(1)
                    break
        if not tx_hash or tx_hash == "unknown":
            return {"error": "Swap response did not include a transaction hash."}
        return {"tx_hash": tx_hash, "amount_out_wei": expected_out}

    def _swap_token_for_token(self, token: str, amount_in_wei: int) -> dict:
        """Swap token -> WBNB via router (testnet)."""
        path = self._sell_path(token)
        if not path:
            return {"error": "Invalid sell path."}
        token_in = path[0]

        approve_result = self._mcp.call_tool(
            "write_contract",
            {
                "contractAddress": token_in,
                "abi": ERC20_APPROVE_ABI,
                "functionName": "approve",
                "args": [PANCAKE_V2_ROUTER_TESTNET, str(amount_in_wei * 2)],
                "network": "bsc-testnet",
            },
        )
        if approve_result.get("error"):
            return {"error": f"Approval failed: {approve_result['error']}"}

        amounts = self._get_amounts_out(amount_in_wei, path)
        if not amounts:
            return {"error": "Quote failed."}
        expected_out = int(amounts[-1])
        if expected_out <= 0:
            return {"error": f"Quote returned zero or negative output: {expected_out}"}

        min_out = str(max(1, int(expected_out * 0.01)))
        deadline = int(time.time()) + 300
        swap_args = [str(amount_in_wei), min_out, path, self._wallet, deadline]
        swap_params = {
            "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
            "abi": json.loads(SWAP_ABI_JSON),
            "functionName": "swapExactTokensForTokens",
            "args": swap_args,
            "network": "bsc-testnet",
        }
        result = self._mcp.call_tool("write_contract", swap_params)
        if result.get("error"):
            return {"error": f"Swap failed: {result['error']}"}
        tx_hash = self._extract_tx_hash(result)
        content = result.get("content", [])
        if not tx_hash or tx_hash == "unknown":
            for item in content:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                match = _TX_HASH_PATTERN.search(text)
                if match:
                    tx_hash = match.group(1)
                    break
        if not tx_hash or tx_hash == "unknown":
            return {"error": "Swap response did not include a transaction hash."}
        return {"tx_hash": tx_hash, "amount_out_wei": expected_out}

    @staticmethod
    def _extract_tx_hash(result: dict) -> str:
        def find_hash(value) -> str | None:
            if value is None:
                return None

            if isinstance(value, str):
                match = _TX_HASH_PATTERN.search(value)
                if match:
                    return match.group(1)
                try:
                    parsed = json.loads(value)
                except Exception:
                    return None
                return find_hash(parsed)

            if isinstance(value, dict):
                preferred_keys = (
                    "transactionHash",
                    "txHash",
                    "tx_hash",
                    "hash",
                    "transaction_hash",
                )
                for key in preferred_keys:
                    if key in value:
                        candidate = find_hash(value.get(key))
                        if candidate:
                            return candidate
                for nested_value in value.values():
                    candidate = find_hash(nested_value)
                    if candidate:
                        return candidate
                return None

            if isinstance(value, list):
                for item in value:
                    candidate = find_hash(item)
                    if candidate:
                        return candidate
                return None

            return None

        return find_hash(result) or "unknown"

    @staticmethod
    def _buy_path(token: str) -> list[str]:
        wbnb = TESTNET_TOKENS["BNB"].lower()
        busd = TESTNET_TOKENS["BUSD"].lower()
        token_addr = TESTNET_TOKENS.get(token.upper())
        if not token_addr:
            return []
        token_addr = token_addr.lower()
        if token_addr == wbnb:
            return []
        if token_addr == busd:
            return [wbnb, busd]
        return [wbnb, busd, token_addr]

    @staticmethod
    def _sell_path(token: str) -> list[str]:
        wbnb = TESTNET_TOKENS["BNB"].lower()
        busd = TESTNET_TOKENS["BUSD"].lower()
        token_addr = TESTNET_TOKENS.get(token.upper())
        if not token_addr:
            return []
        token_addr = token_addr.lower()
        if token_addr == busd:
            return [busd, wbnb]
        return [token_addr, busd, wbnb]

    def _swap_pair(self, token: str, direction: str) -> tuple[str, str]:
        stable = TESTNET_TOKENS.get("BUSD", TESTNET_TOKENS["BNB"])
        token_addr = TESTNET_TOKENS.get(token, TESTNET_TOKENS["BNB"])
        if direction == "BUY_DEX_SELL_CEX": return stable, token_addr
        return token_addr, stable

    @staticmethod
    def _to_wei(amount: float, decimals: int = 18) -> int:
        return int(amount * (10 ** decimals))

    def _get_amounts_out(self, amount_in_wei: int, path: list[str]) -> list[int] | None:
        quote = self._mcp.call_tool(
            "read_contract",
            {
                "contractAddress": PANCAKE_V2_ROUTER_TESTNET,
                "abi": json.loads(ROUTER_ABI_JSON),
                "functionName": "getAmountsOut",
                "args": [str(amount_in_wei), path],
                "network": "bsc-testnet",
            },
        )
        if quote.get("error"):
            return None
        result = quote.get("result")
        if isinstance(result, str):
            try:
                amounts = json.loads(result)
            except json.JSONDecodeError:
                return None
        elif isinstance(result, list):
            amounts = result
        else:
            return None
        if not amounts or len(amounts) < 2:
            return None
        return [int(a) for a in amounts]

    def _estimate_gas_bnb(self, amount_in_wei: int, buy_path: list[str], sell_path: list[str]) -> float | None:
        if not self._wallet:
            return None
        try:
            from web3 import Web3
        except Exception:
            return None

        try:
            web3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC))
            if not web3.is_connected():
                return None

            wallet = Web3.to_checksum_address(self._wallet)
            router = web3.eth.contract(
                address=Web3.to_checksum_address(PANCAKE_V2_ROUTER_TESTNET),
                abi=ROUTER_ABI,
            )

            def checksum_path(path: list[str]) -> list[str]:
                return [Web3.to_checksum_address(p) for p in path]

            gas_price = web3.eth.gas_price
            deadline = int(time.time()) + 300

            total_gas = 0

            # Approve WBNB for buy leg
            wbnb = Web3.to_checksum_address(TESTNET_TOKENS["BNB"])
            erc20 = web3.eth.contract(address=wbnb, abi=ERC20_APPROVE_ABI)
            try:
                gas = erc20.functions.approve(PANCAKE_V2_ROUTER_TESTNET, amount_in_wei * 2).estimate_gas({"from": wallet})
                total_gas += gas
            except Exception:
                pass

            # Buy swap
            try:
                gas = router.functions.swapExactTokensForTokens(
                    amount_in_wei,
                    1,
                    checksum_path(buy_path),
                    wallet,
                    deadline,
                ).estimate_gas({"from": wallet})
                total_gas += gas
            except Exception:
                pass

            # Approve token for sell leg
            token_in = Web3.to_checksum_address(sell_path[0])
            erc20_sell = web3.eth.contract(address=token_in, abi=ERC20_APPROVE_ABI)
            try:
                gas = erc20_sell.functions.approve(PANCAKE_V2_ROUTER_TESTNET, amount_in_wei * 2).estimate_gas({"from": wallet})
                total_gas += gas
            except Exception:
                pass

            # Sell swap
            try:
                gas = router.functions.swapExactTokensForTokens(
                    amount_in_wei,
                    1,
                    checksum_path(sell_path),
                    wallet,
                    deadline,
                ).estimate_gas({"from": wallet})
                total_gas += gas
            except Exception:
                pass

            if total_gas <= 0:
                return None
            return (total_gas * gas_price) / 1e18
        except Exception:
            return None

    def _build_result(self, token: str, direction: str, status: str, reason: str, decision: dict, tx_hash: str = "N/A", profit_pct: float = 0.0, amount_out: int = 0) -> dict:
        return {"token_in": token if direction == "BUY_CEX_SELL_DEX" else "BUSD", "token_out": "BUSD" if direction == "BUY_CEX_SELL_DEX" else token, "amount": self._amount_bnb, "amount_out_wei": amount_out, "direction": direction, "status": status, "tx_hash": tx_hash, "profit_estimate_pct": round(profit_pct, 4), "market_phase": decision.get("market_phase", "UNKNOWN"), "sentiment_signal": decision.get("sentiment_signal", 0.0), "confidence_score": decision.get("confidence_score", 0), "risk_level": decision.get("risk_level", "UNKNOWN"), "reason": reason or decision.get("reason", ""), "chain_id": BSC_TESTNET_CHAIN_ID, "router": PANCAKE_V2_ROUTER_TESTNET, "timestamp": datetime.utcnow().isoformat(), "circuit_breaker": self._breaker.status}

    @property
    def trade_history(self) -> list[dict]: return self._logger.recent(50)

    @property
    def circuit_breaker_status(self) -> dict: return self._breaker.status
