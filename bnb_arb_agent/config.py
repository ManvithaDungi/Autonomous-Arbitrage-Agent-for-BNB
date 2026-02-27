# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # News APIs
    GNEWS_KEY = os.getenv("GNEWS_KEY")
    THENEWSAPI_KEY = os.getenv("THENEWSAPI_KEY")
    CRYPTOPANIC_KEY = os.getenv("CRYPTOPANIC_KEY")

    # Gemini
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    # Targets
    TARGET_TOKENS = ["BNB", "CAKE", "BabyDoge", "BTCB", "ETH"]
    SEARCH_KEYWORDS = [f"{t} price" for t in TARGET_TOKENS] + \
                      ["BNB pump", "BNB dip", "pancakeswap", "BNB listing"]

    # Thresholds
    SENTIMENT_THRESHOLD = 0.3       # Min avg sentiment to flag
    PRICE_DIFF_THRESHOLD = 0.01     # 1% price diff for arb
    POLL_INTERVAL_SECONDS = 60