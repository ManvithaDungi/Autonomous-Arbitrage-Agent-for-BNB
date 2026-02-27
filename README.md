# BNB Arb Intelligence Agent

A full-stack, AI-powered arbitrage and intelligence dashboard for BNB Chain. This project combines on-chain analytics, news/sentiment ingestion, market phase prediction, and automated trade execution using the Model Context Protocol (MCP) and bnbchain-mcp server.

---

## 🚀 Quick Start

1. **Install dependencies:**
	- Python 3.9+
	- `pip install -r requirements.txt` (ensure you have all required packages, including `streamlit`, `requests`, `pandas`, `bs4`, `feedparser`, `pytrends`, `langchain`, `langgraph`, `vaderSentiment`, etc.)
	- Node.js (for MCP server integration)
2. **Set up environment variables:**
	- Copy `.env.example` to `.env` and fill in API keys (GNEWS, THENEWSAPI, CRYPTOPANIC, GOOGLE_API_KEY, BSCSCAN_API_KEY, etc.)
	- Set your MCP server URL and PRIVATE_KEY for blockchain actions.
3. **Run the dashboard:**
	- `streamlit run bnb_arb_agent/dashboard.py`

---

## 🧩 Project Structure & Features

### Main Dashboard
- **dashboard.py**: Streamlit app for the intelligence dashboard. Lets you select a token, run full analysis, and view:
  - On-chain intelligence (7 signal monitors)
  - Sentiment analysis (Gemini + VADER)
  - Market phase prediction (Momentum, Accumulation, Distribution, Volatility Spike)
  - Final decision and recommended action (trade, hold, monitor)

### Core Agents
- **agents/ingestion_agent.py**: Aggregates news, RSS, CryptoPanic, Google Trends, CoinGecko trending, and web scrapes (Bitcointalk, 4chan) for relevant data.
- **agents/analysis_agent.py**: Fuses VADER sentiment and Gemini LLM analysis for robust sentiment scoring.
- **agents/onchain_intelligence_agent.py**: Computes 7 on-chain signals (buy/sell pressure, whale flows, social growth, dev activity, liquidity, narrative, holder distribution) and predicts market phase.
- **agents/decision_agent.py**: Combines sentiment, price data, and on-chain intelligence to recommend and trigger trades.
- **agents/execution_agent.py**: Handles trade execution via MCP server, with pre-flight checks, swap simulation, logging, and circuit breaker.

### Orchestration
- **orchestrator.py**: Runs the full pipeline for all target tokens in a loop (ingestion → intelligence → analysis → decision → execution).

### Config & Tools
- **config.py**: Centralized config, loads all API keys and settings from environment variables.
- **tools/price_fetcher.py**: Async utility for fetching token prices from CoinGecko.
- **tools/scrapers.py**: Async utility for fetching news via GNews or RSS.

---

## 🛠️ Key Features & Checks
- **On-chain intelligence**: 7 monitors for market health and whale activity.
- **Sentiment fusion**: Combines fast VADER and deep Gemini LLM for robust signals.
- **Market phase prediction**: AI-driven phase classifier for actionable insights.
- **Automated trade execution**: Via MCP server, with safety checks and logging.
- **Circuit breaker**: Pauses trading after consecutive failures.
- **Extensible ingestion**: Add new news, social, or on-chain sources easily.

---

## ⚙️ Usage & Customization
- Edit `config.py` or your `.env` to set API keys, MCP server URL, and trading parameters.
- Add/remove tokens in `TARGET_TOKENS` in `config.py`.
- To run the full pipeline in CLI mode: `python bnb_arb_agent/orchestrator.py`
- To use the dashboard: `streamlit run bnb_arb_agent/dashboard.py`

---

## 🧪 Testing & Validation
- All major features are implemented and code is modular.
- Each agent can be tested independently.
- MCP integration is required for live trading; otherwise, the system runs in analysis/simulation mode.
- Check logs and Streamlit output for errors or warnings.

---

## 📂 File-by-File Analysis

- **dashboard.py**: Main UI, orchestrates all agents, displays results, and handles user input.
- **config.py**: Loads all config from environment variables, including API keys and trading settings.
- **agents/ingestion_agent.py**: Fetches and filters news, trends, and social data from multiple sources.
- **agents/analysis_agent.py**: Runs VADER and Gemini LLM, fuses results, and outputs sentiment.
- **agents/onchain_intelligence_agent.py**: Implements all on-chain monitors and market phase prediction.
- **agents/decision_agent.py**: Makes trade/hold/monitor decisions based on all signals and triggers execution.
- **agents/execution_agent.py**: Handles all trade execution logic, MCP calls, logging, and circuit breaker.
- **orchestrator.py**: Runs the full pipeline for all tokens in a loop, suitable for automation.
- **tools/price_fetcher.py**: Async price fetch utility for CoinGecko.
- **tools/scrapers.py**: Async news fetch utility for GNews and RSS.

---

## 📝 Notes
- Ensure all API keys are valid and MCP server is running for full functionality.
- The code is modular and can be extended for new tokens, sources, or blockchains.
- For live trading, use testnet credentials and small amounts first.

---

## 📣 Run the Dashboard

```sh
streamlit run bnb_arb_agent/dashboard.py
```

---

## 📧 Contact & Issues
- For bugs or feature requests, open an issue on the project repository.
- For help with MCP integration, see the official BNB Chain MCP documentation.
