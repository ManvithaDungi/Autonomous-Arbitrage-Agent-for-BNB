"""Sentiment analysis pipeline using VADER fast-scoring and Gemini deep analysis."""

import os
from typing import Optional

import pandas as pd
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from typing import TypedDict, List
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config import Config
from core.logger import get_logger

logger = get_logger(__name__)
config = Config()

os.environ["GOOGLE_API_KEY"] = config.google_api_key

_llm   = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1, max_tokens=2048)
_vader = SentimentIntensityAnalyzer()

_GEMINI_PROMPT = """\
You are a crypto arbitrage analyst specialising in BNB Chain.
Analyse the following recent web content about {token}:{predict_context}

{texts}

Respond strictly in this format:
SENTIMENT: <number from -1.0 to +1.0>
SIGNAL_TYPE: <PUMP_INCOMING | DUMP_INCOMING | STABLE | LISTING_RUMOR | WHALE_ACTIVITY | NEWS_CATALYST>
URGENCY: <LOW | MEDIUM | HIGH>
KEY_INSIGHT: <one sentence>
ARB_OPPORTUNITY: <YES | NO>
"""

_FALLBACK_RESPONSE = (
    "SENTIMENT: 0\nSIGNAL_TYPE: STABLE\nURGENCY: LOW\n"
    "KEY_INSIGHT: Gemini unavailable.\nARB_OPPORTUNITY: NO"
)


class AnalysisState(TypedDict):
    raw_texts:       List[str]
    sources:         List[str]
    vader_scores:    List[float]
    gemini_analysis: str
    predict_signal:  Optional[float]
    final_signal:    float
    token:           str
    summary:         str


def _vader_node(state: AnalysisState) -> AnalysisState:
    scores = [_vader.polarity_scores(t)["compound"] for t in state["raw_texts"]]
    state["vader_scores"] = scores
    if scores:
        logger.info("VADER average for %s: %.3f", state["token"], sum(scores) / len(scores))
    return state


def _gemini_node(state: AnalysisState) -> AnalysisState:
    predict_context = ""
    if (ps := state.get("predict_signal")) is not None:
        prob = round((ps + 1) / 2 * 100, 1)
        predict_context = f"\n\nPrediction market assigns {prob:.1f}% bullish probability for {state['token']}."

    prompt = _GEMINI_PROMPT.format(
        token=state["token"],
        predict_context=predict_context,
        texts="\n---\n".join(state["raw_texts"][:10]),
    )
    try:
        response = _llm.invoke([HumanMessage(content=prompt)])
        state["gemini_analysis"] = response.content
        logger.info("Gemini analysis complete for %s.", state["token"])
    except Exception:
        logger.exception("Gemini API call failed — using fallback response.")
        state["gemini_analysis"] = _FALLBACK_RESPONSE
    return state


def _skip_gemini_node(state: AnalysisState) -> AnalysisState:
    state["gemini_analysis"] = _FALLBACK_RESPONSE
    return state


def _fusion_node(state: AnalysisState) -> AnalysisState:
    gemini_sentiment = 0.0
    for line in state.get("gemini_analysis", "").split("\n"):
        if line.startswith("SENTIMENT:"):
            try:
                gemini_sentiment = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    vader_avg      = sum(state["vader_scores"]) / len(state["vader_scores"]) if state["vader_scores"] else 0.0
    predict_signal = state.get("predict_signal")

    if predict_signal is not None:
        # 50% Gemini (deep context), 25% VADER (fast text), 25% crowd prediction market
        final = 0.50 * gemini_sentiment + 0.25 * vader_avg + 0.25 * predict_signal
    else:
        final = 0.60 * gemini_sentiment + 0.40 * vader_avg

    state["final_signal"] = round(final, 4)
    state["summary"]      = f"signal={final:.3f}"
    logger.info("Final signal for %s: %.4f", state["token"], final)
    return state


def _route_after_vader(state: AnalysisState) -> str:
    vader_avg = sum(state["vader_scores"]) / len(state["vader_scores"]) if state["vader_scores"] else 0.0
    # Only invoke the slower Gemini call when there is meaningful signal or enough data.
    if abs(vader_avg) > 0.1 or len(state["raw_texts"]) > 5:
        return "gemini"
    return "skip_gemini"


def _build_graph() -> any:
    graph = StateGraph(AnalysisState)
    graph.add_node("vader",       _vader_node)
    graph.add_node("gemini",      _gemini_node)
    graph.add_node("skip_gemini", _skip_gemini_node)
    graph.add_node("fusion",      _fusion_node)
    graph.set_entry_point("vader")
    graph.add_conditional_edges("vader", _route_after_vader, {
        "gemini":      "gemini",
        "skip_gemini": "skip_gemini",
    })
    graph.add_edge("gemini",      "fusion")
    graph.add_edge("skip_gemini", "fusion")
    graph.add_edge("fusion",      END)
    return graph.compile()


class AnalysisAgent:
    """LangGraph pipeline: VADER pre-score -> conditional Gemini -> signal fusion."""

    def __init__(self) -> None:
        self._graph = _build_graph()

    def run(self, dataframe: pd.DataFrame, token: str, predict_signal: float = None) -> dict:
        """Run the analysis pipeline on *dataframe* for *token*.

        Args:
            dataframe:      DataFrame with 'title' and 'content' columns.
            token:          Token symbol being analysed (e.g. 'BNB').
            predict_signal: Optional crowd-sourced signal from prediction markets.

        Returns:
            State dict with 'final_signal', 'gemini_analysis', and 'summary'.
        """
        texts = (dataframe["title"] + " " + dataframe["content"]).dropna().tolist()
        if not texts:
            return {"final_signal": predict_signal or 0.0, "summary": "no data", "gemini_analysis": ""}

        return self._graph.invoke(
            AnalysisState(
                raw_texts=       texts[:30],
                sources=         dataframe["source"].tolist(),
                vader_scores=    [],
                gemini_analysis= "",
                predict_signal=  predict_signal,
                final_signal=    0.0,
                token=           token,
                summary=         "",
            )
        )