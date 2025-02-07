import alpaca_trade_api as tradeapi
import os

from dotenv import load_dotenv
load_dotenv(".env")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
BASE_URL = "https://paper-api.alpaca.markets"

api = tradeapi.REST(ALPACA_API_KEY, ALPACA_API_SECRET, BASE_URL, api_version="v2")

def execute_trade(symbol, qty, side, type="market", time_in_force="gtc"):
    try:
        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type=type,
            time_in_force=time_in_force
        )
        print(f"Order submitted: {order}")
    except Exception as e:
        print(f"Error executing trade: {e}")

# Example trade execution (buying NVDA options - dummy example)
execute_trade("NVDA", 1, "buy")