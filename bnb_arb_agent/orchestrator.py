# orchestrator.py (UPDATED)
# Now integrates On-Chain Intelligence into the full pipeline

import time
from datetime import datetime
from agents.ingestion_agent import DataIngestionAgent
from agents.analysis_agent import AnalysisAgent
from agents.decision_agent import DecisionAgent
from agents.onchain_intelligence_agent import OnChainIntelligenceAgent
from config import Config

cfg = Config()


def run_pipeline():
    USE_TESTNET = True   # ← set False when ready for mainnet

    ingestion    = DataIngestionAgent()
    analysis     = AnalysisAgent()
    decision     = DecisionAgent(use_testnet=USE_TESTNET)
    intelligence = OnChainIntelligenceAgent()

    network_label = "tBNB TESTNET" if USE_TESTNET else "BSC MAINNET"
    print(f"  Network: {network_label}")

    print("🚀 BNB Arb Agent v2 — with On-Chain Intelligence")
    print("=" * 55)

    while True:
        cycle_start = datetime.utcnow()
        all_decisions = []

        # ── Step 1: Fetch all web data ──
        df = ingestion.run()
        texts = (df["title"] + " " + df["content"]).dropna().tolist()

        for token in cfg.TARGET_TOKENS:
            print(f"\n{'='*55}")
            print(f"  Analyzing token: {token}")
            print(f"{'='*55}")

            # ── Step 2: On-Chain Intelligence (NEW) ──
            token_texts = [t for t in texts if token.lower() in t.lower()]
            intel_result = intelligence.run(token, token_texts or texts[:20])

            # ── Step 3: Sentiment Analysis ──
            token_df = df[df.apply(
                lambda r: token.lower() in str(r["title"]).lower(), axis=1
            )]
            if token_df.empty:
                token_df = df.head(10)

            analysis_result = analysis.run(token_df, token)

            # ── Step 4: Decision (now enriched with intel) ──
            decision_result = decision.evaluate_with_intelligence(
                analysis_result, intel_result, token
            )

            all_decisions.append({
                "token": token,
                "decision": decision_result,
                "intelligence": intel_result["prediction"],
                "sentiment": analysis_result.get("final_signal", 0)
            })

        # ── Summary ──
        print(f"\n{'='*55}")
        print(f"  CYCLE COMPLETE — {datetime.utcnow().isoformat()}")
        print(f"{'='*55}")

        for d in all_decisions:
            action = d["decision"]["action"]
            phase  = d["intelligence"]["predicted_phase"]
            signal = d["sentiment"]
            icon   = "🔥" if action == "EXECUTE_TRADE" else "👀" if action == "PAPER_TRADE" else "💤"
            line = f"  {icon} {d['token']:6s} | Phase: {phase:25s} | Sentiment: {signal:+.3f} | Action: {action}"

            # Show execution result if a trade was attempted
            exec_result = d["decision"].get("execution_result")
            if exec_result:
                exec_status = exec_result.get("status", "?")
                exec_icon = "✅" if exec_status == "SUCCESS" else "❌" if exec_status == "FAILED" else "⚠️"
                line += f"\n       {exec_icon} Execution: {exec_status}"
                exec_tx = exec_result.get("tx_hash", "N/A")
                if exec_tx and exec_tx != "N/A":
                    line += f" | TX: {exec_tx[:30]}..."

            print(line)

        actionable = [d for d in all_decisions if d["decision"]["action"] in ["EXECUTE_TRADE", "PAPER_TRADE"]]
        if actionable:
            print(f"\n  ⚡ {len(actionable)} ARB OPPORTUNITIES DETECTED!")

        elapsed = (datetime.utcnow() - cycle_start).seconds
        sleep_time = max(10, cfg.POLL_INTERVAL_SECONDS - elapsed)
        print(f"\n  ⏳ Next cycle in {sleep_time}s...\n")
        time.sleep(sleep_time)


if __name__ == "__main__":
    run_pipeline()