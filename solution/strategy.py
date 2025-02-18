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
        symbol = signal["ticker"]
        side = "buy" if signal["direction"] == "b" else "sell"

        # Fetch latest market price for the symbol
        latest_trade = self.api.get_latest_trade(symbol)
        if not latest_trade:
            logger.error(f"Could not fetch price for {symbol}. Skipping trade.")
            return

        price = latest_trade.price  # Latest market price
        available_cash = self.gateway.get_available_cash()

        if available_cash < price:  # Avoid placing an order if we can't afford even 1 share
            logger.error("Not enough cash to buy even 1 share. Skipping trade.")
            return

        # Calculate max quantity that fits within available cash
        qty = int(available_cash / price)

        # If qty is large, use limit order to minimize slippage
        if qty < 50:
            order_type = "market"
        else:
            order_type = "limit"
            price = price * 1.001 if side == "buy" else price * 0.999  # Small buffer

        self.gateway.send_trade(symbol, qty, side, price, type=order_type, time_in_force="gtc")