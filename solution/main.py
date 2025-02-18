from strategy import Strategy
from config import Config

import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def start():
    strat = Strategy(Config)
    strat.start()

if __name__ == "__main__":
    start()
    