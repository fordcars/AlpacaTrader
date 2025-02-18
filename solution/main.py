from strategy import Strategy
from config import Config
import alpaca_trade_api as tradeapi

import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def start():
    config = Config()
    logger.info("Setting up Alpaca API...")
    api = tradeapi.REST(
        config.alpaca_api_key, config.alpaca_api_secret, config.alpaca_base_url, api_version="v2")
    
    strat = Strategy(config, api)
    strat.start()

if __name__ == "__main__":
    start()
    