import asyncio
from typing import List, Dict, Any
import requests


def _coingecko_simple_price(ids: List[str]) -> Dict[str, Any]:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


async def get_prices(ids: List[str]) -> Dict[str, Any]:
    return await asyncio.to_thread(_coingecko_simple_price, ids)
