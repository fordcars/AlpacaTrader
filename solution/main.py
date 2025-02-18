from strategy import Strategy
from config import Config
from alpaca_api import AlpacaAPI

import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def start():
    config = Config()
    logger.info("Setting up Alpaca API...")
    api = AlpacaAPI(config)
    
    strat = Strategy(config, api)
    strat.start()

if __name__ == "__main__":
    start()
