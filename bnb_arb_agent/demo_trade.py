import sys
import io

from agents.execution_agent import ExecutionAgent

# Force UTF-8 for Windows PowerShell
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def run_live_demo(token: str = "BUSD", force_trade: bool = False) -> dict:
    print("🔥 INITIATING LIVE TESTNET TRANSACTION DEMO 🔥")

    agent = ExecutionAgent()

    # Demo signal to trigger execution
    price_gap_pct = 10.0

    perfect_decision = {
        "token": token,
        "direction": "BUY_DEX_SELL_CEX",
        "price_diff_pct": price_gap_pct,
        "market_phase": "HACKATHON_DEMO",
        "sentiment_signal": 1.0,
        "confidence_score": 100,
        "risk_level": "LOW",
        "reason": "Live Execution Demo",
        "force_trade": force_trade,
    }

    print("Sending payload to Execution Agent...\n")
    result = agent.execute_two_leg(perfect_decision)

    if result.get("status") == "SUCCESS":
        amount_out_wei = result.get("amount_out_wei", 0)
        bought_token = float(amount_out_wei) / (10**18)
        spent_wbnb = float(result.get("amount", 0.0))
        profit_wbnb = result.get("profit_wbnb")

        print("\n" + "💰" * 15)
        print("🚀 ARBITRAGE SUCCESS REPORT")
        print(f"   DEX Roundtrip: {spent_wbnb:.6f} WBNB -> {bought_token:.2f} tokens -> WBNB")
        if profit_wbnb is not None:
            print(f"   NET PROFIT: {profit_wbnb:.6f} WBNB")
        else:
            cex_value_wbnb = spent_wbnb * (1 + (price_gap_pct / 100))
            arbitrage_profit_wbnb = cex_value_wbnb - spent_wbnb
            print(f"   NET PROFIT (simulated): {arbitrage_profit_wbnb:.6f} WBNB (~10%)")
        print("💰" * 15)

        buy_tx = result.get("buy_tx_hash", "")
        sell_tx = result.get("sell_tx_hash", "")
        if buy_tx:
            print(f"\nBuy TX: https://testnet.bscscan.com/tx/{buy_tx.replace('BUY:', '')}")
        if sell_tx:
            print(f"Sell TX: https://testnet.bscscan.com/tx/{sell_tx.replace('SELL:', '')}")

        return {
            "status": "SUCCESS",
            "token": token,
            "tx_hash": result.get("tx_hash", ""),
            "spent_wbnb": spent_wbnb,
            "bought_token": bought_token,
            "price_gap_pct": price_gap_pct,
            "profit_wbnb": profit_wbnb,
            "buy_tx_hash": buy_tx,
            "sell_tx_hash": sell_tx,
        }

    return {
        "status": result.get("status", "FAILED"),
        "token": token,
        "tx_hash": result.get("tx_hash", ""),
        "reason": result.get("reason", "Trade failed"),
    }


if __name__ == "__main__":
    run_live_demo()
