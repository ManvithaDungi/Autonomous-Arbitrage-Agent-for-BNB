"""Flask web UI for the BNB Arbitrage Intelligence Agent."""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from flask import Flask, jsonify, render_template, request


POSITIVE_SIGNALS = {
    "BULLISH",
    "HIGH_ENGAGEMENT",
    "VERY_ACTIVE",
    "ACTIVE",
    "INFLOW",
    "ACCUMULATION",
    "GROWING",
    "DISTRIBUTED",
}

NEGATIVE_SIGNALS = {
    "BEARISH",
    "DISTRIBUTION",
    "OUTFLOW",
    "INACTIVE",
    "WHALE_DOMINATED",
    "DUMP_NARRATIVE",
    "FEAR_NARRATIVE",
}

PHASE_META = {
    "MOMENTUM_BUILDING": {"icon": "📈", "color": "#4ade80"},
    "ACCUMULATION_PHASE": {"icon": "💎", "color": "#60a5fa"},
    "DISTRIBUTION_PHASE": {"icon": "🚨", "color": "#f87171"},
    "VOLATILITY_SPIKE_INCOMING": {"icon": "⚡", "color": "#fb923c"},
}

ACTION_COLORS = {
    "EXECUTE_TRADE": "#4ade80",
    "PAPER_TRADE": "#fbbf24",
    "MONITOR": "#60a5fa",
    "HOLD": "#94a3b8",
}

PROCESSING_STEPS = [
    "Searching for news effecting tokens",
    "Searching for malicious smart contracts",
    "Checking pancake swap profits",
    "Result",
]

TOKEN_METADATA = {
    "BNB":  {"name": "Binance Coin", "logoURI": "https://cryptologos.cc/logos/bnb-bnb-logo.png"},
    "BUSD": {"name": "Binance USD", "logoURI": "https://cryptologos.cc/logos/binance-usd-busd-logo.png"},
    "USDT": {"name": "Tether USD", "logoURI": "https://cryptologos.cc/logos/tether-usdt-logo.png"},
    "DAI":  {"name": "Dai Stablecoin", "logoURI": "https://cryptologos.cc/logos/multi-collateral-dai-dai-logo.png"},
    "CAKE": {"name": "PancakeSwap", "logoURI": "https://cryptologos.cc/logos/pancakeswap-cake-logo.png"},
    "BTCB": {"name": "Bitcoin BEP2", "logoURI": "https://cryptologos.cc/logos/bitcoin-btc-logo.png"},
    "ETH":  {"name": "Ethereum", "logoURI": "https://cryptologos.cc/logos/ethereum-eth-logo.png"},
}


def _signal_class(signal: str) -> str:
    if signal in POSITIVE_SIGNALS:
        return "positive"
    if signal in NEGATIVE_SIGNALS:
        return "negative"
    return "neutral"


def _format_currency(value: float) -> str:
    try:
        numeric = float(value)
        return f"${numeric:,.0f}"
    except Exception:
        return "$0"


def _format_tvl(value: float) -> str:
    try:
        numeric = float(value)
    except Exception:
        numeric = 0.0
    if numeric >= 1e9:
        return f"${numeric / 1e9:.2f}B"
    if numeric >= 1e6:
        return f"${numeric / 1e6:.1f}M"
    return _format_currency(numeric)


def _build_monitors(intel: dict[str, Any]) -> list[dict[str, Any]]:
    bp = intel.get("buy_sell_pressure", {})
    wi = intel.get("wallet_inflows", {})
    sg = intel.get("social_growth", {})
    da = intel.get("dev_activity", {})
    lq = intel.get("liquidity", {})
    nk = intel.get("narrative_keywords", {})
    hd = intel.get("holder_distribution", {})

    monitors = [
        {
            "label": "BUY/SELL PRESSURE",
            "signal": bp.get("signal", "—"),
            "class": _signal_class(bp.get("signal", "")),
            "details": [
                f"Buy: {bp.get('buy_pressure', 0)}% | Sell: {bp.get('sell_pressure', 0)}%",
                f"Ratio: {bp.get('ratio', 0)}",
            ],
        },
        {
            "label": "WHALE WALLET FLOWS",
            "signal": wi.get("signal", "—"),
            "class": _signal_class(wi.get("signal", "")),
            "details": [
                f"Large TXs: {wi.get('large_tx_count', 0)}",
                f"Net Flow: {_format_currency(wi.get('net_whale_flow', 0))}",
            ],
        },
        {
            "label": "SOCIAL VELOCITY",
            "signal": sg.get("signal", "—"),
            "class": _signal_class(sg.get("signal", "")),
            "details": [
                f"Score: {sg.get('social_score', 0)}/100",
                f"Reddit Active: {sg.get('reddit_active_48h', 0):,}",
            ],
        },
        {
            "label": "DEV ACTIVITY",
            "signal": da.get("signal", "—"),
            "class": _signal_class(da.get("signal", "")),
            "details": [
                f"Commits/wk: {da.get('commits_last_week', 0)}",
                f"Last commit: {da.get('last_commit_hours_ago', 999):.0f}h ago",
            ],
        },
        {
            "label": "LIQUIDITY CHANGES",
            "signal": lq.get("liquidity_signal", "—"),
            "class": _signal_class(lq.get("liquidity_signal", "")),
            "details": [
                f"TVL: {_format_tvl(lq.get('tvl_usd', 0))}",
                f"24h Δ: {lq.get('tvl_change_24h_pct', 0):+.2f}%",
            ],
        },
        {
            "label": "NARRATIVE KEYWORDS",
            "signal": nk.get("dominant_narrative", "—"),
            "class": _signal_class(nk.get("signal", "")),
            "details": [
                f"Confidence: {nk.get('narrative_confidence', 0)}%",
                f"Signal: {nk.get('signal', '—')}",
            ],
        },
        {
            "label": "HOLDER DISTRIBUTION",
            "signal": hd.get("distribution_signal", "—"),
            "class": _signal_class(hd.get("distribution_signal", "")),
            "details": [
                f"Top 10 Hold: {hd.get('top10_concentration_pct', 0):.1f}%",
            ],
        },
    ]
    return monitors


def _build_result(token: str, dataframe, intel: dict, sentiment: dict, decision: dict) -> dict[str, Any]:
    pred = intel.get("prediction", {})
    phase = pred.get("predicted_phase", "UNKNOWN")
    phase_meta = PHASE_META.get(phase, {"icon": "🔍", "color": "#94a3b8"})

    cols = [c for c in ["source", "title", "timestamp"] if c in dataframe.columns]
    sample_rows = dataframe[cols].head(20).fillna("").to_dict(orient="records")

    phase_probs = pred.get("phase_probabilities", {})
    phase_probs_sorted = sorted(phase_probs.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "token": token,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "fetched_count": len(dataframe),
        "source_count": dataframe["source"].nunique() if "source" in dataframe.columns else 0,
        "sample_rows": sample_rows,
        "prediction": {
            "phase": phase,
            "confidence": pred.get("confidence", 0),
            "risk_level": pred.get("risk_level", "MEDIUM"),
            "recommendation": pred.get("recommendation", ""),
            "phase_probs": phase_probs_sorted,
            "icon": phase_meta["icon"],
            "color": phase_meta["color"],
        },
        "monitors": _build_monitors(intel.get("intelligence", {})),
        "sentiment": {
            "final_signal": sentiment.get("final_signal", 0),
            "summary": sentiment.get("summary", ""),
        },
        "decision": {
            "price_diff_pct": decision.get("price_diff_pct", 0),
            "direction": decision.get("direction", "—"),
            "confidence": decision.get("confidence_score", 0),
            "risk_level": decision.get("risk_level", "MEDIUM"),
            "action": decision.get("action", "MONITOR"),
            "action_color": ACTION_COLORS.get(decision.get("action"), "#94a3b8"),
        },
    }


def _get_param(name: str, default: str | None = None) -> str | None:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if name in payload:
            return payload.get(name)
    if name in request.form:
        return request.form.get(name)
    return request.args.get(name, default)


def _resolve_token_address(token: str | None, address: str | None) -> tuple[str | None, str | None]:
    if address:
        return token, address
    if not token:
        return None, None
    try:
        from core.constants import MAINNET_TOKENS, TESTNET_TOKENS

        return token, MAINNET_TOKENS.get(token) or TESTNET_TOKENS.get(token)
    except Exception:
        return token, None


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["CORS_ALLOW_ORIGIN"] = os.getenv("CORS_ALLOW_ORIGIN", "http://localhost:3000")

    def _add_cors_headers(response):
        origin = request.headers.get("Origin") or app.config["CORS_ALLOW_ORIGIN"]
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.before_request
    def _handle_options():
        if request.method == "OPTIONS":
            response = app.make_default_options_response()
            return _add_cors_headers(response)

    @app.after_request
    def _apply_cors(response):
        return _add_cors_headers(response)

    @app.route("/", methods=["GET"])
    def index():
        tokens = ["BNB"]
        error = None
        try:
            from config import Config

            tokens = Config().target_tokens
        except Exception as exc:
            error = f"Config warning: {exc}"

        return render_template("index.html", tokens=tokens, result=None, error=error)

    @app.route("/api/steps", methods=["GET"])
    def api_steps():
        return jsonify({"steps": PROCESSING_STEPS, "count": len(PROCESSING_STEPS)})

    @app.route("/api/tokens", methods=["GET"])
    def api_tokens():
        try:
            from core.constants import TESTNET_TOKENS

            tokens = []
            for symbol, address in TESTNET_TOKENS.items():
                if symbol == "BNB":
                    continue
                meta = TOKEN_METADATA.get(symbol, {})
                tokens.append({
                    "symbol": symbol,
                    "name": meta.get("name", symbol),
                    "address": address,
                    "decimals": 18,
                    "logoURI": meta.get("logoURI", ""),
                    "tradeable": True,
                })
            return jsonify({"tokens": tokens, "count": len(tokens)})
        except Exception as exc:
            return jsonify({"tokens": [], "error": str(exc)}), 500

    @app.route("/api/best-token", methods=["GET"])
    def api_best_token():
        try:
            from config import Config
            from core.constants import TESTNET_TOKENS
            from agents.ingestion_agent import DataIngestionAgent
            from agents.analysis_agent import AnalysisAgent
            from agents.decision_agent import DecisionAgent
            from agents.onchain_intelligence_agent import OnChainIntelligenceAgent

            config = Config()
            tokens = [t for t in config.target_tokens if t in TESTNET_TOKENS and t != "BNB"]
            if not tokens:
                return jsonify({"error": "No supported tokens configured."}), 400

            ingestion = DataIngestionAgent()
            analysis = AnalysisAgent()
            decision_agent = DecisionAgent(use_testnet=True)
            intelligence = OnChainIntelligenceAgent()

            dataframe = ingestion.run()
            texts = (dataframe["title"] + " " + dataframe["content"]).dropna().tolist()

            scored: list[dict[str, Any]] = []
            for token in tokens:
                token_texts = [t for t in texts if token.lower() in t.lower()]
                intel = intelligence.run(token, token_texts or texts[:20])

                token_df = dataframe[
                    dataframe["title"].astype(str).str.contains(token, case=False, na=False)
                ]
                if token_df.empty:
                    token_df = dataframe.head(10)

                sentiment = analysis.run(token_df, token)
                decision = decision_agent.evaluate_with_intelligence(sentiment, intel, token)

                scored.append({
                    "token": token,
                    "action": decision.get("action"),
                    "confidence": decision.get("confidence_score", 0),
                    "risk_level": decision.get("risk_level", "MEDIUM"),
                    "price_diff_pct": decision.get("price_diff_pct", 0),
                })

            action_rank = {"EXECUTE_TRADE": 3, "PAPER_TRADE": 2, "MONITOR": 1, "HOLD": 0}
            scored.sort(key=lambda d: (action_rank.get(d["action"], 0), d["confidence"]), reverse=True)
            best = scored[0]
            return jsonify({"best": best, "ranked": scored})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/ingestion", methods=["GET", "POST"])
    def api_ingestion():
        try:
            from agents.ingestion_agent import DataIngestionAgent

            dataframe = DataIngestionAgent().run()
            sample_titles = (
                dataframe["title"].fillna("").head(10).tolist()
                if "title" in dataframe.columns
                else []
            )
            response = {
                "step": PROCESSING_STEPS[0],
                "status": "ok",
                "items": len(dataframe),
                "sources": dataframe["source"].nunique() if "source" in dataframe.columns else 0,
                "sample_titles": sample_titles,
            }
            return jsonify(response)
        except Exception as exc:
            return jsonify({"step": PROCESSING_STEPS[0], "status": "error", "error": str(exc)}), 500

    @app.route("/api/audit", methods=["GET", "POST"])
    def api_audit():
        token = _get_param("token")
        address = _get_param("address")
        token, address = _resolve_token_address(token, address)
        if not address:
            return jsonify({
                "step": PROCESSING_STEPS[1],
                "status": "error",
                "error": "Missing token address. Provide ?address= or ?token=.",
            }), 400

        try:
            from agents.auditor import audit_token

            safe = audit_token(address)
            return jsonify({
                "step": PROCESSING_STEPS[1],
                "status": "ok",
                "token": token,
                "address": address,
                "safe": bool(safe),
                "signal": "SAFE_TO_TRADE" if safe else "DO_NOT_TRADE",
            })
        except Exception as exc:
            return jsonify({"step": PROCESSING_STEPS[1], "status": "error", "error": str(exc)}), 500

    @app.route("/api/pancake", methods=["GET", "POST"])
    def api_pancake():
        token = _get_param("token", "BNB") or "BNB"
        testnet_flag = str(_get_param("testnet", "true")).lower() in {"1", "true", "yes"}
        try:
            from agents.decision_agent import _cex_price
            from tools.price_fetcher import DEXPriceFetcher

            cex = _cex_price(token)
            dex_price = DEXPriceFetcher(use_testnet=testnet_flag).get_dex_price(token)
            cex_price = cex.get("price", 0.0)
            price_diff = 0.0
            direction = "NONE"
            if cex_price > 0 and dex_price > 0:
                price_diff = abs(cex_price - dex_price) / cex_price
                direction = "BUY_DEX_SELL_CEX" if dex_price < cex_price else "BUY_CEX_SELL_DEX"

            return jsonify({
                "step": PROCESSING_STEPS[2],
                "status": "ok",
                "token": token,
                "dex_price": dex_price,
                "cex_price": cex_price,
                "price_diff_pct": round(price_diff * 100, 3),
                "direction": direction,
                "network": "BSC Testnet" if testnet_flag else "BSC Mainnet",
            })
        except Exception as exc:
            return jsonify({"step": PROCESSING_STEPS[2], "status": "error", "error": str(exc)}), 500

    @app.route("/api/result", methods=["GET", "POST"])
    def api_result():
        token = _get_param("token", "BNB") or "BNB"
        try:
            from agents.ingestion_agent import DataIngestionAgent
            from agents.analysis_agent import AnalysisAgent
            from agents.decision_agent import DecisionAgent
            from agents.onchain_intelligence_agent import OnChainIntelligenceAgent

            ingestion = DataIngestionAgent()
            analysis = AnalysisAgent()
            decision_agent = DecisionAgent(use_testnet=True)
            intelligence = OnChainIntelligenceAgent()

            dataframe = ingestion.run()
            texts = (dataframe["title"] + " " + dataframe["content"]).dropna().tolist()
            token_texts = [t for t in texts if token.lower() in t.lower()]

            intel = intelligence.run(token, token_texts or texts[:20])
            token_df = dataframe[
                dataframe["title"].astype(str).str.contains(token, case=False, na=False)
            ]
            if token_df.empty:
                token_df = dataframe.head(10)

            sentiment = analysis.run(token_df, token)
            decision = decision_agent.evaluate_with_intelligence(sentiment, intel, token)

            result = _build_result(token, dataframe, intel, sentiment, decision)
            return jsonify({
                "step": PROCESSING_STEPS[3],
                "status": "ok",
                "result": result,
            })
        except Exception as exc:
            return jsonify({"step": PROCESSING_STEPS[3], "status": "error", "error": str(exc)}), 500

    @app.route("/api/trade", methods=["POST", "GET"])
    def api_trade():
        token_requested = _get_param("token", "BUSD") or "BUSD"
        token = token_requested
        warning = None
        try:
            from core.constants import TESTNET_TOKENS
            if token.upper() not in TESTNET_TOKENS or token.upper() == "BNB":
                token = "BUSD"
                warning = f"Requested token {token_requested} not supported for demo trade. Using BUSD."
        except Exception:
            pass
        try:
            from demo_trade import run_live_demo

            result = run_live_demo(token=token)
            status_code = 200 if result.get("status") == "SUCCESS" else 400
            payload = {"step": "Trade", "status": "ok", "result": result, "token_requested": token_requested, "token_used": token}
            if warning:
                payload["warning"] = warning
            return jsonify(payload), status_code
        except Exception as exc:
            return jsonify({"step": "Trade", "status": "error", "error": str(exc)}), 500

    @app.route("/run", methods=["POST"])
    def run_analysis():
        token = request.form.get("token", "BNB")
        error = None
        result = None
        tokens = [token]

        try:
            from config import Config
            from agents.ingestion_agent import DataIngestionAgent
            from agents.analysis_agent import AnalysisAgent
            from agents.decision_agent import DecisionAgent
            from agents.onchain_intelligence_agent import OnChainIntelligenceAgent

            tokens = Config().target_tokens
            ingestion = DataIngestionAgent()
            analysis = AnalysisAgent()
            decision_agent = DecisionAgent(use_testnet=True)
            intelligence = OnChainIntelligenceAgent()

            dataframe = ingestion.run()
            texts = (dataframe["title"] + " " + dataframe["content"]).dropna().tolist()
            token_texts = [t for t in texts if token.lower() in t.lower()]

            intel = intelligence.run(token, token_texts or texts[:20])

            token_df = dataframe[
                dataframe["title"].astype(str).str.contains(token, case=False, na=False)
            ]
            if token_df.empty:
                token_df = dataframe.head(10)

            sentiment = analysis.run(token_df, token)
            decision = decision_agent.evaluate_with_intelligence(sentiment, intel, token)

            result = _build_result(token, dataframe, intel, sentiment, decision)
        except Exception as exc:
            error = f"Run failed: {exc}"

        return render_template("index.html", tokens=tokens, result=result, error=error)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=53421, debug=True)
