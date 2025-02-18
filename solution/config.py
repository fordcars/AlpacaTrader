import os

from dotenv import load_dotenv
load_dotenv(".env")

class Config:
    alpaca_api_key = os.getenv("ALPACA_API_KEY")
    alpaca_api_secret = os.getenv("ALPACA_API_SECRET")
    alpaca_base_url = "https://paper-api.alpaca.markets"
    redis_port = os.getenv("REDIS_PORT")

    # Limits
    max_open_exposure = 300000  # Maximum open exposure in dollars
    max_price = 100000  # Maximum qty per trade in dollars (limit orders)
