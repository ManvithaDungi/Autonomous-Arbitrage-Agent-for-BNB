# dashboard.py (UPGRADED)
# Full intelligence dashboard with all 7 signal monitors + phase prediction

import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(
    page_title="BNB Arb Intelligence",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Dark theme CSS ──
st.markdown("""
<style>
body, .stApp { background: #0a0e1a; color: #e2e8f0; }
.metric-card {
    background: #111827;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 16px;
    margin: 8px 0;
}
.phase-badge {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 14px;
}
.MOMENTUM_BUILDING      { background: #14532d; color: #4ade80; }
.ACCUMULATION_PHASE     { background: #1e3a5f; color: #60a5fa; }
.DISTRIBUTION_PHASE     { background: #7f1d1d; color: #f87171; }
.VOLATILITY_SPIKE_INCOMING { background: #451a03; color: #fb923c; }
.signal-green { color: #4ade80; font-weight: bold; }
.signal-red   { color: #f87171; font-weight: bold; }
.signal-yellow{ color: #fbbf24; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Header ──
st.markdown("# 🧠 BNB Chain AI Intelligence Agent")
st.markdown("*On-chain signals + sentiment analysis + market phase prediction*")
st.divider()

# ── Controls ──
col_token, col_run = st.columns([2, 1])
with col_token:
    token = st.selectbox("Token", ["BNB", "CAKE", "BTCB", "ETH"], label_visibility="collapsed")
with col_run:
    run_btn = st.button("🚀 Run Full Analysis", use_container_width=True, type="primary")

if run_btn:
    from agents.ingestion_agent import DataIngestionAgent
    from agents.analysis_agent import AnalysisAgent
    from agents.decision_agent import DecisionAgent
    from agents.onchain_intelligence_agent import OnChainIntelligenceAgent

    # ── Data Ingestion ──
    with st.spinner("🌐 Fetching from all web sources..."):
        df = DataIngestionAgent().run()
    st.success(f"✅ {len(df)} items from {df['source'].nunique()} sources")

    with st.expander("📋 Raw Data Sample"):
        st.dataframe(df[["source", "title", "timestamp", "engagement"]].head(20), use_container_width=True)

    # ── On-Chain Intelligence ──
    with st.spinner("⛓️ Running on-chain intelligence..."):
        texts = (df["title"] + " " + df["content"]).dropna().tolist()
        token_texts = [t for t in texts if token.lower() in t.lower()]
        intel = OnChainIntelligenceAgent().run(token, token_texts or texts[:20])

    # ── Sentiment Analysis ──
    with st.spinner("🤖 Running Gemini sentiment analysis..."):
        token_df = df[df["title"].str.contains(token, case=False, na=False)]
        sentiment = AnalysisAgent().run(token_df if not token_df.empty else df.head(10), token)

    # ── Decision ──
    with st.spinner("🎯 Making decision..."):
        decision = DecisionAgent().evaluate_with_intelligence(sentiment, intel, token)

    st.divider()

    # ════════════════════════════════
    # PREDICTION BANNER
    # ════════════════════════════════
    pred = intel["prediction"]
    phase = pred["predicted_phase"]
    phase_colors = {
        "MOMENTUM_BUILDING": ("📈", "#4ade80"),
        "ACCUMULATION_PHASE": ("💎", "#60a5fa"),
        "DISTRIBUTION_PHASE": ("🚨", "#f87171"),
        "VOLATILITY_SPIKE_INCOMING": ("⚡", "#fb923c"),
    }
    icon, color = phase_colors.get(phase, ("🔍", "#94a3b8"))

    st.markdown(f"""
    <div style="background:#111827;border:2px solid {color};border-radius:12px;padding:20px;margin:16px 0;">
        <div style="font-size:13px;color:#94a3b8;margin-bottom:4px;">PREDICTED MARKET PHASE</div>
        <div style="font-size:28px;font-weight:bold;color:{color};">{icon} {phase.replace('_', ' ')}</div>
        <div style="font-size:14px;color:#e2e8f0;margin-top:8px;">{pred['recommendation']}</div>
        <div style="margin-top:12px;">
            <span style="background:#1e293b;padding:4px 12px;border-radius:20px;font-size:12px;margin-right:8px;">
                Confidence: {pred['confidence']}/100
            </span>
            <span style="background:#1e293b;padding:4px 12px;border-radius:20px;font-size:12px;">
                Risk: {pred['risk_level']}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════
    # 7 SIGNAL MONITORS (2 rows)
    # ════════════════════════════════
    st.markdown("### 📡 Signal Monitors")
    intel_data = intel["intelligence"]

    def signal_color(sig):
        positive = ["BULLISH", "HIGH_ENGAGEMENT", "VERY_ACTIVE", "ACTIVE", "INFLOW",
                    "ACCUMULATION", "GROWING", "DISTRIBUTED"]
        negative = ["BEARISH", "DISTRIBUTION", "OUTFLOW", "INACTIVE", "WHALE_DOMINATED",
                    "DUMP_NARRATIVE", "FEAR_NARRATIVE"]
        if sig in positive: return "🟢"
        if sig in negative: return "🔴"
        return "🟡"

    r1 = st.columns(4)
    r2 = st.columns(3)

    # Row 1
    with r1[0]:
        bp = intel_data.get("buy_sell_pressure", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">BUY/SELL PRESSURE</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(bp.get('signal',''))} {bp.get('signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Buy: {bp.get('buy_pressure',0)}% | Sell: {bp.get('sell_pressure',0)}%</div>
            <div style="font-size:12px;color:#94a3b8;">Ratio: {bp.get('ratio',0)}</div>
        </div>""", unsafe_allow_html=True)

    with r1[1]:
        wi = intel_data.get("wallet_inflows", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">WHALE WALLET FLOWS</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(wi.get('signal',''))} {wi.get('signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Large TXs: {wi.get('large_tx_count',0)}</div>
            <div style="font-size:12px;color:#94a3b8;">Net Flow: ${wi.get('net_whale_flow',0):,.0f}</div>
        </div>""", unsafe_allow_html=True)

    with r1[2]:
        sg = intel_data.get("social_growth", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">SOCIAL VELOCITY</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(sg.get('signal',''))} {sg.get('signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Score: {sg.get('social_score',0)}/100</div>
            <div style="font-size:12px;color:#94a3b8;">Reddit Active: {sg.get('reddit_active_48h',0):,}</div>
        </div>""", unsafe_allow_html=True)

    with r1[3]:
        da = intel_data.get("dev_activity", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">DEV ACTIVITY</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(da.get('signal',''))} {da.get('signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Commits/wk: {da.get('commits_last_week',0)}</div>
            <div style="font-size:12px;color:#94a3b8;">Last commit: {da.get('last_commit_hours_ago',999):.0f}h ago</div>
        </div>""", unsafe_allow_html=True)

    # Row 2
    with r2[0]:
        lq = intel_data.get("liquidity", {})
        tvl = lq.get("tvl_usd", 0)
        tvl_str = f"${tvl/1e9:.2f}B" if tvl > 1e9 else f"${tvl/1e6:.1f}M"
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">LIQUIDITY CHANGES</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(lq.get('liquidity_signal',''))} {lq.get('liquidity_signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">TVL: {tvl_str}</div>
            <div style="font-size:12px;color:#94a3b8;">24h Δ: {lq.get('tvl_change_24h_pct',0):+.2f}%</div>
        </div>""", unsafe_allow_html=True)

    with r2[1]:
        nk = intel_data.get("narrative_keywords", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">NARRATIVE KEYWORDS</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(nk.get('signal',''))} {nk.get('dominant_narrative','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Confidence: {nk.get('narrative_confidence',0)}%</div>
            <div style="font-size:12px;color:#94a3b8;">Signal: {nk.get('signal','—')}</div>
        </div>""", unsafe_allow_html=True)

    with r2[2]:
        hd = intel_data.get("holder_distribution", {})
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:11px;color:#94a3b8;">HOLDER DISTRIBUTION</div>
            <div style="font-size:20px;margin:4px 0;">{signal_color(hd.get('distribution_signal',''))} {hd.get('distribution_signal','—')}</div>
            <div style="font-size:12px;color:#94a3b8;">Top 10 Hold: {hd.get('top10_concentration_pct',0):.1f}%</div>
        </div>""", unsafe_allow_html=True)

    # ════════════════════════════════
    # SENTIMENT + FINAL DECISION
    # ════════════════════════════════
    st.divider()
    st.markdown("### 🎯 Sentiment + Final Decision")
    c1, c2, c3, c4 = st.columns(4)

    action_color = {"EXECUTE_TRADE": "#4ade80", "PAPER_TRADE": "#fbbf24",
                    "MONITOR": "#60a5fa", "HOLD": "#94a3b8"}.get(decision["action"], "#94a3b8")

    c1.metric("Sentiment Signal", f"{sentiment.get('final_signal', 0):+.3f}", "Gemini+VADER fusion")
    c2.metric("Price Diff", f"{decision['price_diff_pct']}%", decision["direction"])
    c3.metric("Confidence", f"{decision['confidence_score']}/100", decision["risk_level"] + " risk")
    c4.markdown(f"""
    <div style="text-align:center;padding-top:8px;">
        <div style="font-size:11px;color:#94a3b8;">RECOMMENDED ACTION</div>
        <div style="font-size:22px;font-weight:bold;color:{action_color};">{decision['action']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Phase probabilities bar chart
    st.markdown("### 📊 Phase Probability Breakdown")
    probs = pred.get("phase_probabilities", {})
    if probs:
        prob_df = pd.DataFrame(list(probs.items()), columns=["Phase", "Probability %"])
        prob_df = prob_df.sort_values("Probability %", ascending=False)
        st.bar_chart(prob_df.set_index("Phase"), color="#3b82f6")

else:
    # ── Welcome screen ──
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;color:#475569;">
        <div style="font-size:64px;margin-bottom:16px;">🧠</div>
        <div style="font-size:20px;font-weight:bold;color:#94a3b8;">Select a token and click Run Full Analysis</div>
        <div style="font-size:14px;margin-top:8px;">
            Monitors: Buy/Sell Pressure · Whale Wallets · Social Velocity · Dev Activity ·
            Liquidity · Narrative Keywords · Holder Distribution
        </div>
        <div style="font-size:14px;margin-top:4px;color:#60a5fa;">
            Predicts: Momentum Building · Distribution · Accumulation · Volatility Spikes
        </div>
    </div>
    """, unsafe_allow_html=True)
