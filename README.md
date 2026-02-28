# BNB Chain AI Arbitrage Agent

An AI-powered arbitrage agent for BNB Chain that monitors sentiment, on-chain intelligence, and DEX/CEX price spreads to identify and execute arbitrage opportunities on BSC Testnet.

## How It Works

1. Every 2 minutes, the agent fetches news from 10+ sources (RSS, GNews, Reddit, 4chan, CoinGecko trends, CryptoPanic)
2. VADER scores all articles for sentiment; Gemini performs deep analysis on relevant ones
3. On-chain intelligence checks whale wallet flows, dev activity, social growth, TVL, and holder distribution
4. Decision agent combines all signals into a confidence score and confirms whether an arb opportunity exists
5. If confirmed (≥0.5% DEX/CEX price diff and confidence ≥60), `ExecutionAgent` routes the trade through the BNBChain MCP server
6. The MCP server signs and broadcasts the PancakeSwap swap on BSC Testnet using your private key

## Decision Logic

| Condition | Action |
|---|---|
| `arb_confirmed = False` or `confidence < 20` | HOLD |
| `confidence ≥ 60` | EXECUTE_TRADE |
| `confidence ≥ 30` | PAPER_TRADE (logged only, no real tx) |

`arb_confirmed` triggers when **any** of:
- Sentiment >0.3 **and** DEX/CEX diff >0.5%
- Gemini returns `ARB_OPPORTUNITY: YES`
- Real on-chain DEX price differs from CoinGecko by ≥0.5%
- Momentum phase detected with >0.3% spread

## Prerequisites

- Python 3.12+
- Node.js 18+ (for the BNBChain MCP server)
- A BSC Testnet wallet funded with tBNB — faucet: https://testnet.bnbchain.org/faucet-smart

## Setup

### 1. Create environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp bnb_arb_agent/env.example .env
```

Fill in `.env`:

```env
# Required
GOOGLE_API_KEY=your_gemini_api_key
PRIVATE_KEY=your_64_char_hex_private_key     # BSC Testnet only — never use mainnet key
WALLET_ADDRESS=0xYourWalletAddress            # Must match PRIVATE_KEY
MCP_SERVER_URL=http://localhost:3001

# Execution settings
EXECUTION_ENABLED=true
TRADE_AMOUNT_BNB=0.01
MIN_PROFIT_THRESHOLD=0.005
SLIPPAGE_TOLERANCE=0.02
CIRCUIT_BREAKER_MAX_FAILURES=3
CIRCUIT_BREAKER_COOLDOWN_MIN=15

# Optional — improves data quality
GNEWS_KEY=...
CRYPTOPANIC_KEY=...
BSCSCAN_API_KEY=...
GITHUB_TOKEN=...
```

## Running

You need **two terminals**.

### Terminal 1 — BNBChain MCP server

```powershell
.\start_mcp.ps1
```

Wait for `INFO: Starting sse server on port 3001` before starting the agent.

> If port 3001 is already in use:
> ```powershell
> Get-NetTCPConnection -LocalPort 3001 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
> .\start_mcp.ps1
> ```

### Terminal 2 — Agent

```powershell
.venv\Scripts\python.exe bnb_arb_agent\orchestrator.py
```

### Optional — Streamlit Dashboard

```powershell
.venv\Scripts\python.exe -m streamlit run bnb_arb_agent\dashboard.py
```

Open http://localhost:8501

## Tests

```powershell
.venv\Scripts\python.exe -m pytest bnb_arb_agent\tests\ -v
```

20 unit tests covering decision logic and DEX price fallback chain.

## Make Shortcuts

```
make run        # Run the orchestrator
make test       # Run pytest
make dashboard  # Launch Streamlit dashboard
make mcp        # Start the MCP server
```
