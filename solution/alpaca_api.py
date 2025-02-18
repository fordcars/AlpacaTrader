from config import Config
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

class AlpacaAPI:
    def __init__(self, config: Config):
        self.trade = TradingClient(config.alpaca_api_key, config.alpaca_api_secret, paper=True)
        self.hist = StockHistoricalDataClient(config.alpaca_api_key, config.alpaca_api_secret)