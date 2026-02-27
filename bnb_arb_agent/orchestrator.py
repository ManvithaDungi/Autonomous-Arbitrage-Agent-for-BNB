# orchestrator.py
import time
from agents.ingestion_agent import DataIngestionAgent
from agents.analysis_agent import AnalysisAgent
from agents.decision_agent import DecisionAgent
from config import Config

cfg = Config()

def run_pipeline():
    ingestion = DataIngestionAgent()
    analysis = AnalysisAgent()
    decision = DecisionAgent()

    print("🚀 BNB Arb Agent Starting...")

    while True:
        all_decisions = []

        # Fetch once, analyze per token
        df = ingestion.run()

        for token in cfg.TARGET_TOKENS:
            print(f"\n📍 Analyzing {token}...")
            # Filter data relevant to this token
            token_df = df[df.apply(
                lambda r: token.lower() in str(r["title"]).lower() or token.lower() in str(r["content"]).lower(),
                axis=1
            )]
            if token_df.empty:
                token_df = df.head(10)   # Fallback to general data

            analysis_result = analysis.run(token_df, token)
            decision_result = decision.evaluate(analysis_result, token)
            all_decisions.append(decision_result)

        # Show actionable decisions
        actionable = [d for d in all_decisions if d["action"] in ["EXECUTE_TRADE", "PAPER_TRADE"]]
        if actionable:
            print(f"\n🔥 {len(actionable)} ARB OPPORTUNITIES DETECTED!")

        print(f"\n⏳ Sleeping {cfg.POLL_INTERVAL_SECONDS}s...\n")
        time.sleep(cfg.POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_pipeline()