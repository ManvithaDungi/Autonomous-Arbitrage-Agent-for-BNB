import sys
import io
import requests
import time
import json

# Force UTF-8 for Windows PowerShell
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SIMULATION_MODE = False # REAL TRADE MODE
THRESHOLD_USD = 0.50

def discover_polymarket_events():
    """Fetches real, live markets with massive liquidity from Polymarket."""
    try:
        # We grab the top 20 most active, open events right now
        url = "https://gamma-api.polymarket.com/events?limit=20&active=true&closed=false"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"DEBUG: Polymarket API failed - {e}", file=sys.stderr)
        return []

def get_dex_price(token_address):
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/bsc/tokens/{token_address}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return float(res.json()['data']['attributes']['price_usd'])
        return None
    except Exception:
        return None

def monitor():
    print("🚀 AI Arbitrage Engine: Polymarket Cross-Chain Discovery Mode", flush=True)
    base_token = {
        "name": "BUSD", 
        "price_address": "0xe9e7cea3dedca5984780bafc599bd69add087d56", # Mainnet for real DEX price
        "trade_address": "0xed24fc36d5ee211ea25a80239fb8c4cfd80f12ee"   # Testnet for execution
    }

    while True:
        print("\n📡 Fetching LIVE global markets from Polymarket...", flush=True)
        events = discover_polymarket_events()
        
        if not events:
            time.sleep(10)
            continue

        print("📊 Fetching base DEX price...", flush=True)
        price_dex = get_dex_price(base_token['price_address'])
        
        if price_dex is None:
            time.sleep(10)
            continue

        print(f"✅ Base DEX Price locked at: ${price_dex:.4f}\n", flush=True)

        # Iterate through Polymarket's nested JSON structure
        for event in events:
            markets = event.get('markets', [])
            for market in markets:
                # Truncate long questions so the terminal looks clean
                market_title = market.get('question', 'Unknown Market')[:45] 
                
                try:
                    # Polymarket returns prices as stringified JSON arrays (e.g., '["0.65", "0.35"]')
                    outcomes = market.get('outcomes', '[]')
                    prices = market.get('outcomePrices', '[]')
                    
                    if isinstance(outcomes, str): outcomes = json.loads(outcomes)
                    if isinstance(prices, str): prices = json.loads(prices)
                    
                    if not prices or len(prices) == 0:
                        continue
                        
                    # Grab the live probability of the first outcome (Usually 'Yes')
                    price_predict = float(prices[0])
                    
                except Exception:
                    continue

                if price_predict == 0.0:
                    continue

                gas_fee = 0.50
                amount_bnb = 0.05
                capital_usd = amount_bnb * 600.0 
                
                # The Arbitrage Math
                gross_profit = ((capital_usd / price_dex) * price_predict) - capital_usd
                net_profit = gross_profit - gas_fee

                print(f"   ∟ {market_title:<45} | Poly Price: ${price_predict:.4f} | Net: ${net_profit:.2f}", flush=True)

                # Trigger the Smart Contract if the math clears the threshold
                if net_profit > THRESHOLD_USD:
                    print(f"\n🔥 CROSS-CHAIN OPPORTUNITY DETECTED! Triggering BNB Smart Contract...", flush=True)
                    signal = {
                        "action": "TRADE",
                        "token": base_token['trade_address'],
                        "token_name": base_token['name'],
                        "amount": str(amount_bnb),
                        "is_simulation": SIMULATION_MODE
                    }
                    print(f"SIGNAL:{json.dumps(signal)}", flush=True)
                    
                    # Deep sleep after firing a trade so the terminal pauses for your demo
                    time.sleep(120) 

                # Micro-delay for terminal readability
                time.sleep(0.1)

        print("\n🏁 Finished scanning Polymarket. Polling again...", flush=True)
        time.sleep(10) 

if __name__ == "__main__":
    monitor()