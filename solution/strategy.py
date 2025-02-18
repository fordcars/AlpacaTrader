from config import Config
from gateway import Gateway
from signal_stream import SignalStream

import logging
logger = logging.getLogger(__name__)

class Strategy:
    def __init__(self, config: Config):
        self.config = config
        self.gateway = Gateway(config)
        self.signals = SignalStream(config)
        self.api = self.gateway.api
    
    def start(self):
        logger.info("Starting strategy!")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        logger.info(f"Received signal: {signal}")

        # Fetch latest market price for the symbol
        latest_trade = self.api.get_latest_trade(signal["ticker"])
        if not latest_trade:
            logger.error(f"Could not fetch price for {signal['ticker']}. Skipping trade.")
            return

        price = latest_trade.price  # Latest market price
        available_cash = self.gateway.get_available_cash()

        if available_cash < price:  # Avoid placing an order if we can't afford even 1 share
            logger.error("Not enough cash to buy even 1 share. Skipping trade.")
            return

        # Calculate max quantity that fits within available cash
        qty = int(available_cash / price)

        self.gateway.send_trade(
            symbol=signal["ticker"],
            qty=qty,
            side="buy" if signal["direction"] == "b" else "sell",
            price=None,
            type="market",
            time_in_force="gtc"
        )