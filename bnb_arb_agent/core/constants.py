"""Immutable constants: network addresses, ABIs, and external URLs."""

import json


# BSC Mainnet token addresses (checksummed)
MAINNET_TOKENS: dict[str, str] = {
    "BNB":      "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "CAKE":     "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "BTCB":     "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    "ETH":      "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BUSD":     "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "USDT":     "0x55d398326f99059fF775485246999027B3197955",
    "BabyDoge": "0xc748673057861a797275CD8A068AbB95A902e8de",
}

# BSC Testnet token addresses
TESTNET_TOKENS: dict[str, str] = {
    "BNB":  "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",
    "CAKE": "0xa35062EA4301827E69e6008E18d14f5d8C3DBA3e",
    "BUSD": "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee",
    "USDT": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
    "DAI":  "0x8a9424745056Eb399FD19a0EC26A14316684e274",
}

# PancakeSwap router addresses
PANCAKE_V2_ROUTER_MAINNET = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
PANCAKE_V2_ROUTER_TESTNET = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"

# BSC chain IDs
BSC_MAINNET_CHAIN_ID = 56
BSC_TESTNET_CHAIN_ID = 97

# GeckoTerminal pool addresses for price discovery (token/USDT on BSC)
GECKOTERMINAL_POOLS: dict[str, str] = {
    "BNB":  "0x36696169c63e42cd08ce11f5deebbcebae652050",
    "CAKE": "0x7cd05e4c3bf1e7b758a91fdb9e7fc1c0f7f24538",
    "BTCB": "0x46cf1cf8c69595804ba91dfdd8d6b960c9b0a7c4",
    "ETH":  "0x74e4716e431f45807dcf19f284c7aa99f18a4fbc",
}

# CoinGecko coin IDs for CEX price lookup
COINGECKO_IDS: dict[str, str] = {
    "BNB":      "binancecoin",
    "CAKE":     "pancakeswap-token",
    "BTCB":     "bitcoin-bep2",
    "ETH":      "ethereum",
    "BabyDoge": "baby-doge-coin",
    "BUSD":     "binance-usd",
    "USDT":     "tether",
}

# PancakeSwap v2 router ABI — only the functions the agent needs
ROUTER_ABI: list[dict] = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn",  "type": "uint256"},
            {"internalType": "address[]", "name": "path",   "type": "address[]"},
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Swap execution ABI fragment
SWAP_EXACT_TOKENS_FOR_TOKENS_ABI: list[dict] = [
    {
        "inputs": [
            {"name": "amountIn",     "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path",         "type": "address[]"},
            {"name": "to",           "type": "address"},
            {"name": "deadline",     "type": "uint256"},
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# JSON-serialised forms for MCP tool calls
ROUTER_ABI_JSON = json.dumps(ROUTER_ABI)
SWAP_ABI_JSON   = json.dumps(SWAP_EXACT_TOKENS_FOR_TOKENS_ABI)

# PancakeSwap v3 subgraph endpoints (tried in order)
SUBGRAPH_ENDPOINTS: list[str] = [
    "https://api.goldsky.com/api/public/project_clk9dujce3e1f2nzgkrg13gj9/subgraphs/pancakeswap-v3-bsc/latest/gn",
    "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v3-bsc",
]

# BSC RPC endpoints
BSC_MAINNET_RPC = "https://bsc-dataseed1.binance.org/"
BSC_TESTNET_RPC = "https://data-seed-prebsc-1-s1.binance.org:8545/"
