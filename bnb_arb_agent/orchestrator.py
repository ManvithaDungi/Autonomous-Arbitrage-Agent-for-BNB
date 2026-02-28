"""Main orchestration loop — runs the full analysis pipeline on a timed cycle."""

import time
from datetime import datetime

from agents.analysis_agent import AnalysisAgent
from agents.decision_agent import DecisionAgent
from agents.ingestion_agent import DataIngestionAgent
from agents.onchain_intelligence_agent import OnChainIntelligenceAgent
from config import Config
from core.logger import get_logger

logger = get_logger(__name__)
config = Config()


def run_pipeline() -> None:
    use_testnet = True  # Switch to False when deploying to mainnet

    ingestion    = DataIngestionAgent()
    analysis     = AnalysisAgent()
    decision     = DecisionAgent(use_testnet=use_testnet)
    intelligence = OnChainIntelligenceAgent()

    network = "BSC Testnet" if use_testnet else "BSC Mainnet"
    logger.info("Starting BNB Arb Agent on %s.", network)

    while True:
        cycle_start = datetime.utcnow()

        dataframe = ingestion.run()
        texts     = (dataframe["title"] + " " + dataframe["content"]).dropna().tolist()

        all_decisions = []

        for token in config.target_tokens:
            logger.info("Analysing token: %s", token)

            token_texts  = [t for t in texts if token.lower() in t.lower()]
            intel_result = intelligence.run(token, token_texts or texts[:20])

            token_df = dataframe[
                dataframe.apply(lambda r: token.lower() in str(r["title"]).lower(), axis=1)
            ]
            if token_df.empty:
                token_df = dataframe.head(10)

            analysis_result = analysis.run(token_df, token)

            decision_result = decision.evaluate_with_intelligence(
                analysis_result, intel_result, token
            )

            all_decisions.append({
                "token":        token,
                "decision":     decision_result,
                "intelligence": intel_result["prediction"],
                "sentiment":    analysis_result.get("final_signal", 0.0),
            })

        actionable = [d for d in all_decisions if d["decision"]["action"] in ("EXECUTE_TRADE", "PAPER_TRADE")]
        if actionable:
            logger.info("%d arbitrage opportunity/ies found this cycle.", len(actionable))

        elapsed    = (datetime.utcnow() - cycle_start).seconds
        sleep_time = max(10, config.poll_interval_seconds - elapsed)
        logger.info("Cycle complete. Next run in %ds.", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    run_pipeline()