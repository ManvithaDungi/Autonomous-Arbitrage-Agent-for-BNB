"""DEX price fetcher with multiple fallback sources."""

import time
import functools
from typing import Callable

import requests
from web3 import Web3

from core.constants import (
    MAINNET_TOKENS,
    TESTNET_TOKENS,
    SUBGRAPH_ENDPOINTS,
    ROUTER_ABI,
    PANCAKE_V2_ROUTER_MAINNET,
    PANCAKE_V2_ROUTER_TESTNET,
    BSC_MAINNET_RPC,
    BSC_TESTNET_RPC,
)
from core.logger import get_logger

logger = get_logger(__name__)

_BUSD_MAINNET  = MAINNET_TOKENS["BUSD"]
_WBNB_MAINNET  = MAINNET_TOKENS["BNB"]


def _retry(max_attempts: int = 3, backoff: float = 1.5) -> Callable:
    """Retry decorator with exponential backoff for flaky HTTP calls."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = 1.0
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ValueError) as exc:
                    if attempt == max_attempts:
                        raise
                    logger.debug("Attempt %d failed (%s) — retrying in %.1fs.", attempt, exc, delay)
                    time.sleep(delay)
                    delay *= backoff
        return wrapper
    return decorator


class DEXPriceFetcher:
    """Fetches real DEX prices using PancakeSwap subgraph and on-chain router.

    Two sources are tried in order. CoinGecko is intentionally excluded here
    because it is also used as the CEX reference, which would produce a zero
    price differential and suppress all arbitrage signals.
    """

    def __init__(self, use_testnet: bool = False) -> None:
        self._use_testnet = use_testnet
        self._tokens      = TESTNET_TOKENS if use_testnet else MAINNET_TOKENS

        rpc    = BSC_TESTNET_RPC if use_testnet else BSC_MAINNET_RPC
        router = PANCAKE_V2_ROUTER_TESTNET if use_testnet else PANCAKE_V2_ROUTER_MAINNET

        web3 = Web3(Web3.HTTPProvider(rpc))
        self._router = web3.eth.contract(
            address=Web3.to_checksum_address(router),
            abi=ROUTER_ABI,
        )

    def get_dex_price(self, symbol: str) -> float:
        """Return the DEX price in USD for *symbol*, or 0.0 if unavailable."""
        price = self._price_from_subgraph(symbol)
        if price > 0:
            logger.info("DEX price for %s from subgraph: $%.4f", symbol, price)
            return price

        price = self._price_from_router(symbol)
        if price > 0:
            logger.info("DEX price for %s from router: $%.4f", symbol, price)
            return price

        logger.warning("No on-chain price found for %s.", symbol)
        return 0.0

    @_retry(max_attempts=2)
    def _price_from_subgraph(self, symbol: str) -> float:
        token_address = self._tokens.get(symbol, "").lower()
        if not token_address:
            return 0.0

        query = '{ token(id: "%s") { derivedUSD tokenDayData(first:1, orderBy:date, orderDirection:desc) { priceUSD } } }' % token_address

        for endpoint in SUBGRAPH_ENDPOINTS:
            try:
                response = requests.post(endpoint, json={"query": query}, timeout=6)
                response.raise_for_status()
                token_data = response.json().get("data", {}).get("token") or {}

                price = float(token_data.get("derivedUSD") or 0)
                if price > 0:
                    return price

                day_data = token_data.get("tokenDayData", [])
                if day_data:
                    return float(day_data[0].get("priceUSD", 0))
            except (requests.RequestException, ValueError, KeyError):
                continue

        return 0.0

    @_retry(max_attempts=2)
    def _price_from_router(self, symbol: str) -> float:
        token_address = self._tokens.get(symbol)
        if not token_address:
            return 0.0

        stable  = TESTNET_TOKENS.get("USDT", _BUSD_MAINNET) if self._use_testnet else _BUSD_MAINNET
        wbnb    = self._tokens.get("BNB", _WBNB_MAINNET)

        path = (
            [Web3.to_checksum_address(wbnb), Web3.to_checksum_address(stable)]
            if symbol == "BNB"
            else [
                Web3.to_checksum_address(token_address),
                Web3.to_checksum_address(wbnb),
                Web3.to_checksum_address(stable),
            ]
        )
        try:
            amounts = self._router.functions.getAmountsOut(Web3.to_wei(1, "ether"), path).call()
            return amounts[-1] / 1e18
        except Exception as exc:
            # Contract reverts when a pair does not exist (e.g. token not on this network).
            logger.debug("Router call reverted for %s: %s", symbol, exc)
            return 0.0