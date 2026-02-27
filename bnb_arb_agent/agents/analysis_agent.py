# agents/analysis_agent.py

import os
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from typing import TypedDict, List
import pandas as pd
from config import Config

cfg = Config()
os.environ["GOOGLE_API_KEY"] = cfg.GOOGLE_API_KEY

# ─── State Schema for LangGraph ───
class AnalysisState(TypedDict):
    raw_texts: List[str]
    sources: List[str]
    vader_scores: List[float]
    gemini_analysis: str
    final_signal: float
    token: str
    summary: str

# ─── Gemini LLM ───
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",   # Current model
    temperature=0.1,
    max_tokens=2048
)

vader = SentimentIntensityAnalyzer()

# ─────────────────────────────────────────
# NODE 1: VADER Fast Pre-Scoring
# ─────────────────────────────────────────
def vader_scoring_node(state: AnalysisState) -> AnalysisState:
    scores = []
    for text in state["raw_texts"]:
        score = vader.polarity_scores(text)["compound"]  # -1 to +1
        scores.append(score)
    state["vader_scores"] = scores
    print(f"📊 VADER avg: {sum(scores)/len(scores):.3f}" if scores else "No scores")
    return state

# ─────────────────────────────────────────
# NODE 2: GEMINI Deep Analysis
# ─────────────────────────────────────────
def gemini_analysis_node(state: AnalysisState) -> AnalysisState:
    token = state["token"]
    # Sample top 10 texts to avoid token overload
    sample = state["raw_texts"][:10]
    combined = "\n---\n".join(sample)

    prompt = f"""You are a crypto arbitrage analyst specializing in BNB Chain.
Analyze the following recent web content about {token}:

{combined}

Provide:
1. SENTIMENT: Overall sentiment score from -1.0 (very bearish) to +1.0 (very bullish). Just the number.
2. SIGNAL_TYPE: One of [PUMP_INCOMING, DUMP_INCOMING, STABLE, LISTING_RUMOR, WHALE_ACTIVITY, NEWS_CATALYST]
3. URGENCY: LOW / MEDIUM / HIGH
4. KEY_INSIGHT: One sentence explaining the dominant narrative
5. ARB_OPPORTUNITY: YES or NO — Is there likely a price lag between DEX and CEX?

Format strictly as:
SENTIMENT: <number>
SIGNAL_TYPE: <type>
URGENCY: <level>
KEY_INSIGHT: <text>
ARB_OPPORTUNITY: <YES/NO>
"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        state["gemini_analysis"] = response.content
        print(f"🤖 Gemini Analysis:\n{response.content}")
    except Exception as e:
        print(f"[Gemini Error] {e}")
        state["gemini_analysis"] = "SENTIMENT: 0\nSIGNAL_TYPE: STABLE\nURGENCY: LOW\nKEY_INSIGHT: API error\nARB_OPPORTUNITY: NO"

    return state

# ─────────────────────────────────────────
# NODE 3: Fuse VADER + Gemini → Final Signal
# ─────────────────────────────────────────
def signal_fusion_node(state: AnalysisState) -> AnalysisState:
    # Parse Gemini output
    analysis = state.get("gemini_analysis", "")
    gemini_sentiment = 0.0
    arb_opportunity = False

    for line in analysis.split("\n"):
        if line.startswith("SENTIMENT:"):
            try:
                gemini_sentiment = float(line.split(":")[1].strip())
            except:
                pass
        if line.startswith("ARB_OPPORTUNITY:"):
            arb_opportunity = "YES" in line

    vader_avg = sum(state["vader_scores"]) / len(state["vader_scores"]) if state["vader_scores"] else 0

    # Weighted fusion: 60% Gemini (context-aware) + 40% VADER (fast)
    final_signal = 0.6 * gemini_sentiment + 0.4 * vader_avg

    state["final_signal"] = round(final_signal, 4)
    state["summary"] = f"Signal: {final_signal:.3f} | ARB: {arb_opportunity} | Sources: {len(state['raw_texts'])}"
    print(f"✅ Final Signal: {final_signal:.3f} (Gemini: {gemini_sentiment}, VADER: {vader_avg:.3f})")
    return state

# ─── Routing Logic ───
def should_deep_analyze(state: AnalysisState) -> str:
    vader_avg = sum(state["vader_scores"]) / len(state["vader_scores"]) if state["vader_scores"] else 0
    # Only call Gemini (expensive) if VADER shows movement
    if abs(vader_avg) > 0.1 or len(state["raw_texts"]) > 5:
        return "gemini"
    return "skip_gemini"

def skip_gemini_node(state: AnalysisState) -> AnalysisState:
    state["gemini_analysis"] = "SENTIMENT: 0\nSIGNAL_TYPE: STABLE\nURGENCY: LOW\nKEY_INSIGHT: Low sentiment, skipped Gemini\nARB_OPPORTUNITY: NO"
    return state

# ─── Build LangGraph ───
def build_analysis_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("vader_scoring", vader_scoring_node)
    graph.add_node("gemini_analysis", gemini_analysis_node)
    graph.add_node("skip_gemini", skip_gemini_node)
    graph.add_node("signal_fusion", signal_fusion_node)

    graph.set_entry_point("vader_scoring")
    graph.add_conditional_edges("vader_scoring", should_deep_analyze, {
        "gemini": "gemini_analysis",
        "skip_gemini": "skip_gemini"
    })
    graph.add_edge("gemini_analysis", "signal_fusion")
    graph.add_edge("skip_gemini", "signal_fusion")
    graph.add_edge("signal_fusion", END)

    return graph.compile()

# ─── Analysis Agent Class ───
class AnalysisAgent:
    def __init__(self):
        self.graph = build_analysis_graph()

    def run(self, df: pd.DataFrame, token: str) -> dict:
        texts = (df["title"] + " " + df["content"]).dropna().tolist()
        if not texts:
            return {"final_signal": 0, "summary": "No data", "gemini_analysis": ""}

        initial_state = AnalysisState(
            raw_texts=texts[:30],   # Cap to avoid token limits
            sources=df["source"].tolist(),
            vader_scores=[],
            gemini_analysis="",
            final_signal=0.0,
            token=token,
            summary=""
        )

        result = self.graph.invoke(initial_state)
        return result