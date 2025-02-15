import os

from dotenv import load_dotenv
load_dotenv(".env")

class Config:
    alpaca_api_key = os.getenv("ALPACA_API_KEY")
    alpaca_api_secret = os.getenv("ALPACA_API_SECRET")
    alpaca_base_url = "https://paper-api.alpaca.markets"
    redis_port = 6379

    # Trading
    starting_cash = 100000

    # Limits
    max_open_exposure = 100000  # Maximum open exposure in dollars
    max_price = 10000  # Maximum qty per trade in dollars (limit orders)
