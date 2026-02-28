import requests
import sys
import io
import time

# Force UTF-8 for Windows PowerShell
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BSCSCAN_API_KEY = "RSIZ5MWCWP8BPVIKNXYZAZ5QYAMDFEJ64E"
# Allow minor warnings (like stablecoin mints), but block actual scams
MAX_ALLOWED_RISK = 25 

def fetch_contract_code(token_address):
    print(f"📡 Fetching source code for {token_address}...", flush=True)
    url = f"https://api.etherscan.io/v2/api?chainid=56&module=contract&action=getsourcecode&address={token_address}&apikey={BSCSCAN_API_KEY}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('status') == '1' and data.get('result') and data['result'][0].get('SourceCode'):
            print("✅ Source code downloaded successfully!")
            return data['result'][0]['SourceCode']
        return None
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

def scan_for_vulnerabilities(source_code):
    print("\n🔍 Initiating Security Scan...", flush=True)
    
    risk_score = 0
    warnings = []
    code_lower = source_code.lower()

    # 1. The Honeypot Check (Critical)
    if "require(msg.sender == owner" in code_lower and "transfer" in code_lower and "transferownership" not in code_lower:
        warnings.append("🚨 CRITICAL RISK: Transfer restricted to owner (Potential Honeypot/Can't Sell).")
        risk_score += 100

    # 2. The Hidden Mint Check (Warning)
    if "function mint(" in code_lower or "function _mint(" in code_lower:
        if "onlyowner" in code_lower or "auth" in code_lower:
            warnings.append("⚠️ MEDIUM RISK: Owner can mint tokens (Normal for stablecoins, risky for memes).")
            risk_score += 20

    # 3. The Blacklist Check (Warning)
    if "isblacklisted" in code_lower or "blacklist" in code_lower:
        warnings.append("⚠️ MEDIUM RISK: Contract contains a blacklist (Normal for USDT, risky for others).")
        risk_score += 20

    # 4. Modifiable Tax/Fees Check (High Risk)
    if "settax" in code_lower or "setfee" in code_lower:
        warnings.append("🚨 HIGH RISK: Owner can modify trading taxes/fees at any time.")
        risk_score += 40

    # Add this to your existing scan_for_vulnerabilities
    if "isExcludedFromFee" in code_lower or "isExcludedFromReward" in code_lower:
        warnings.append("⚠️ WARNING: Certain wallets (Owner) are exempt from taxes/rules.")
        risk_score += 15

    if risk_score <= MAX_ALLOWED_RISK:
        print(f"🛡️ Scan Complete: Acceptable risk level. (Risk Score: {risk_score})")
        for warning in warnings: print(f"   ∟ {warning}")
        return True
    else:
        print(f"🛑 Scan Complete: Malicious patterns found! (Risk Score: {risk_score})")
        for warning in warnings: print(f"   ∟ {warning}")
        return False

def audit_token(token_address):
    print(f"🤖 AI Auditor Agent Started", flush=True)
    source_code = fetch_contract_code(token_address)
    
    if source_code:
        is_safe = scan_for_vulnerabilities(source_code)
        if is_safe:
            print("\n🟢 AGENT SIGNAL: SAFE TO TRADE")
            return True
        else:
            print("\n🔴 AGENT SIGNAL: DO NOT TRADE - MALICIOUS CONTRACT")
            return False
    else:
        print("\n🟡 AGENT SIGNAL: UNVERIFIED - SKIP TRADE")
        return False

if __name__ == "__main__":
    tokens_to_test = {
        "WBNB (Perfectly Clean, 0 Risk)": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "BUSD (Has safe Mint function)": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
        "SafeMoon V1 (Scammy Modifiable Taxes)": "0x8076C74C5e3F5852037F31Ff0093Eeb8c8ADd8D3",
        "USDT (Blacklist Present, No Fee Manipulation)": "0x55d398326f99059fF775485246999027B3197955",
        "PancakeSwap CAKE (Standard DEX Minting Logic)": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
        "Ankr Reward Staked BNB (Transparent Staking Roles)": "0xE867207604E6E4E1F33C21C1eC45C9FfC6fE7c92",
        "Standard ERC20 (OpenZeppelin Mock)": "Custom Mock",
        "\"The Switch\" Scam (Owner Controlled Trading Toggle)": "Varies",
        "The Tax Trap (Adjustable Buy/Sell Fees)": "Varies",
        "Hidden Honeypot (Owner Controlled Transfer Check)": "Varies"
    }

    print("=========================================")
    print("🛡️ INITIATING AI SMART CONTRACT AUDITOR 🛡️")
    print("=========================================\n")

    for name, address in tokens_to_test.items():
        print(f"\n🧪 TESTING: {name}")
        audit_token(address)
        print("-" * 40)
        time.sleep(1)