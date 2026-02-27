# tools/price_fetcher.py
# FIXED: Multiple DEX price sources — PancakeSwap v3 subgraph + direct router fallback

import requests
from web3 import Web3
from config import Config

cfg = Config()

# ── Token addresses (BSC Mainnet) ──
TOKEN_ADDRESSES = {
    "BNB":      "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",   # WBNB
    "CAKE":     "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "BTCB":     "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    "ETH":      "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BUSD":     "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "USDT":     "0x55d398326f99059fF775485246999027B3197955",
    "BabyDoge": "0xc748673057861a797275CD8A068AbB95A902e8de",
}

# ── tBNB Testnet addresses ──
TESTNET_ADDRESSES = {
    "BNB":  "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",   # tWBNB
    "CAKE": "0xa35062EA4301827E69e6008E18d14f5d8C3DBA3e",   # testnet CAKE
    "USDT": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
}

BUSD_ADDRESS   = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
WBNB_ADDRESS   = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# PancakeSwap v2 Router ABI (only getAmountsOut needed)
ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# PancakeSwap v2 Router addresses
PANCAKE_V2_ROUTER_MAINNET = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
PANCAKE_V2_ROUTER_TESTNET = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"


class DEXPriceFetcher:
    """
    Fetches real DEX prices using 3 methods (tries each in order):
    1. PancakeSwap v3 Subgraph (new URL)
    2. PancakeSwap v2 on-chain router call
    3. CoinGecko fallback (so price is never $0)
    """

    COINGECKO_IDS = {
        "BNB":      "binancecoin",
        "CAKE":     "pancakeswap-token",
        "BTCB":     "bitcoin-bep2",
        "ETH":      "ethereum",
        "BabyDoge": "baby-doge-coin",
        "BUSD":     "binance-usd",
        "USDT":     "tether",
    }

    def __init__(self, use_testnet=False):
        self.use_testnet = use_testnet
        rpc = "https://data-seed-prebsc-1-s1.binance.org:8545/" if use_testnet \
              else "https://bsc-dataseed1.binance.org/"
        self.w3 = Web3(Web3.HTTPProvider(rpc))
        router_addr = PANCAKE_V2_ROUTER_TESTNET if use_testnet else PANCAKE_V2_ROUTER_MAINNET
        self.router = self.w3.eth.contract(
            address=Web3.to_checksum_address(router_addr),
            abi=ROUTER_ABI
        )

    # ── Method 1: PancakeSwap v3 Subgraph (goldsky) ──
    def _price_from_subgraph_v3(self, token_symbol: str) -> float:
        addrs = TESTNET_ADDRESSES if self.use_testnet else TOKEN_ADDRESSES
        token_addr = addrs.get(token_symbol, "").lower()
        if not token_addr:
            return 0.0

        # Try goldsky subgraph (active as of 2025)
        endpoints = [
            "https://api.goldsky.com/api/public/project_clk9dujce3e1f2nzgkrg13gj9/subgraphs/pancakeswap-v3-bsc/latest/gn",
            "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v3-bsc",
        ]

        query = """
        {
          token(id: "%s") {
            derivedUSD
            tokenDayData(first: 1, orderBy: date, orderDirection: desc) {
              priceUSD
            }
          }
        }
        """ % token_addr

        for endpoint in endpoints:
            try:
                res = requests.post(endpoint, json={"query": query}, timeout=6).json()
                token_data = res.get("data", {}).get("token", {})
                if token_data:
                    price = float(token_data.get("derivedUSD", 0) or 0)
                    if price > 0:
                        return price
                    # Try day data
                    day_data = token_data.get("tokenDayData", [])
                    if day_data:
                        return float(day_data[0].get("priceUSD", 0))
            except Exception as e:
                continue

        return 0.0

    # ── Method 2: On-chain router call ──
    def _price_from_router(self, token_symbol: str) -> float:
        addrs = TESTNET_ADDRESSES if self.use_testnet else TOKEN_ADDRESSES
        token_addr = addrs.get(token_symbol)
        stable_addr = TESTNET_ADDRESSES.get("USDT", BUSD_ADDRESS) if self.use_testnet else BUSD_ADDRESS

        if not token_addr:
            return 0.0

        try:
            # For BNB/WBNB, path is direct: WBNB -> BUSD
            wbnb = TESTNET_ADDRESSES.get("BNB", WBNB_ADDRESS) if self.use_testnet else WBNB_ADDRESS

            if token_symbol == "BNB":
                path = [
                    Web3.to_checksum_address(wbnb),
                    Web3.to_checksum_address(stable_addr)
                ]
            else:
                path = [
                    Web3.to_checksum_address(token_addr),
                    Web3.to_checksum_address(wbnb),
                    Web3.to_checksum_address(stable_addr)
                ]

            amount_in = Web3.to_wei(1, 'ether')
            amounts_out = self.router.functions.getAmountsOut(amount_in, path).call()
            price = amounts_out[-1] / 1e18
            return price
        except Exception as e:
            print(f"    [Router price error for {token_symbol}] {e}")
            return 0.0

    # ── Method 3: CoinGecko fallback ──
    def _price_from_coingecko(self, token_symbol: str) -> float:
        coin_id = self.COINGECKO_IDS.get(token_symbol, token_symbol.lower())
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
            data = requests.get(url, timeout=6).json()
            return data.get(coin_id, {}).get("usd", 0.0)
        except:
            return 0.0

    def get_dex_price(self, token_symbol: str) -> float:
        """
        Real DEX price only — subgraph first, router second.
        Does NOT fall back to CoinGecko (that's the CEX price source — same price = 0% diff).
        Returns 0.0 if both fail, which keeps price_diff at 0 rather than fake 0%.
        """
        # Method 1: Subgraph
        price = self._price_from_subgraph_v3(token_symbol)
        if price > 0:
            print(f"    💱 DEX price ({token_symbol}) from subgraph: ${price:.4f}")
            return price

        # Method 2: On-chain PancakeSwap v2 router
        price = self._price_from_router(token_symbol)
        if price > 0:
            print(f"    💱 DEX price ({token_symbol}) from router: ${price:.4f}")
            return price

        print(f"    ⚠️  No real DEX price found for {token_symbol} — skipping comparison")
        return 0.0