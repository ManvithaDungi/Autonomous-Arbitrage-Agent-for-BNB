# dashboard.py
import streamlit as st
import pandas as pd
from agents.ingestion_agent import DataIngestionAgent
from agents.analysis_agent import AnalysisAgent
from agents.decision_agent import DecisionAgent
from config import Config

cfg = Config()
st.set_page_config(page_title="BNB Arb Agent", layout="wide")
st.title("🤖 BNB Chain AI Arbitrage Agent")

col1, col2, col3 = st.columns(3)
col1.metric("Sources", "10+", "RSS + Reddit + Twitter + News")
col2.metric("Model", "Gemini 1.5 Flash", "LangGraph")
col3.metric("Chain", "BNB Testnet", "PancakeSwap")

token = st.selectbox("Select Token", cfg.TARGET_TOKENS)

if st.button("🚀 Run Full Pipeline"):
    with st.spinner("Fetching from all web sources..."):
        df = DataIngestionAgent().run()
    st.success(f"✅ Collected {len(df)} items from {df['source'].nunique()} sources")
    st.dataframe(df[["source", "title", "timestamp", "engagement"]].head(30))

    with st.spinner("Analyzing with Gemini + VADER..."):
        token_df = df[df["title"].str.contains(token, case=False, na=False)]
        result = AnalysisAgent().run(token_df if not token_df.empty else df.head(10), token)

    st.subheader("📊 Analysis Result")
    st.metric("Final Signal", f"{result['final_signal']:.3f}", "(-1 bearish → +1 bullish)")
    st.text_area("Gemini Analysis", result.get("gemini_analysis", ""), height=200)

    with st.spinner("Making decision..."):
        decision = DecisionAgent().evaluate(result, token)

    st.subheader("🎯 Decision")
    action_color = "🟢" if decision["action"] == "EXECUTE_TRADE" else "🟡" if decision["action"] == "PAPER_TRADE" else "🔴"
    st.markdown(f"### {action_color} {decision['action']}")
    st.json(decision)
