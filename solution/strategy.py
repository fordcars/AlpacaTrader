import time
import threading

import numpy as np
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
        self.stop_current_trade = threading.Event()  # Event flag to stop execution
        self.execution_threads = {}  # Store running execution threads

    def start(self):
        logger.info("Starting strategy!")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        logger.info(f"Received signal: {signal}")
        symbol = signal["ticker"]
        side = "buy" if signal["direction"] == "b" else "sell"

        # Stop any ongoing execution for the same symbol
        if symbol in self.execution_threads:
            self.stop_execution()
            self.execution_threads[symbol].join()
            del self.execution_threads[symbol]

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
        execution_thread = threading.Thread(target=self._execute_dynamic_trade, args=(symbol, qty, side))
        execution_thread.daemon = True  # Ensures thread exits when program stops
        execution_thread.start()
        self.execution_threads[symbol] = execution_thread

    def _get_average_daily_volume(self, symbol, days=5):
        bars = self.api.get_bars(symbol, "1D", limit=days).df  # Get daily bars for the last `days`
        
        if bars.empty:
            logger.warning(f"No volume data for {symbol}. Returning 0.")
            return 0

        avg_volume = bars["volume"].mean()  # Calculate average daily volume
        return avg_volume
    
    def _get_historical_data(self, symbol, interval="1Min", time_period="60Min"):
        bars = self.api.get_bars(symbol, interval, limit=int(time_period[:-3])).df  # Convert "60Min" → 60 bars

        if bars.empty:
            logger.warning(f"No historical data for {symbol}.")
            return None

        return bars  # Returns a Pandas DataFrame
    
    def stop_execution(self):
        self.stop_current_trade.set()

    # Dynamic approach
    def _execute_dynamic_trade(self, symbol, total_qty, side):
        # Fetch market data (latest price & volume)
        latest_trade = self.api.get_latest_trade(symbol)
        if not latest_trade:
            logger.error(f"Could not fetch price for {symbol}. Skipping trade.")
            return

        price = latest_trade.price
        volume = self._get_average_daily_volume(symbol)

        logger.debug(f"Market Data: {symbol} Price=${price}, Daily Volume={volume}")

        # **Step 1: Small Orders (Execute Market Order)**
        if total_qty < 50:
            logger.info(f"Executing {total_qty} {symbol} at market price")
            self.gateway.send_trade(symbol, total_qty, side, price=None, type="market")
            return

        # **Step 2: Medium Orders (Use Limit Orders with Smart Pricing)**
        if 50 <= total_qty < 500:
            limit_price = price * 1.001 if side == "buy" else price * 0.999  # Adjust 0.1%
            logger.info(f"Placing limit order for {total_qty} {symbol} @ ${limit_price:.2f}")
            self.gateway.send_trade(symbol, total_qty, side, price=limit_price, type="limit")
            return

        # **Step 3: Large Orders (VWAP or TWAP Execution)**
        if total_qty >= 500:
            if volume > 1_000_000:  # High liquidity → Use VWAP
                logger.info(f"Using VWAP execution for {total_qty} {symbol}")
                self._execute_vwap(symbol, total_qty, side)
            else:  # Low liquidity → Use TWAP
                logger.info(f"Using TWAP execution for {total_qty} {symbol}")
                self._execute_twap(symbol, total_qty, side)

    def _execute_vwap(self, symbol, total_qty, side):
        bars = self._get_historical_data(symbol, interval="1Min", time_period="60Min")
        bars["vwap"] = (bars["volume"] * (bars["high"] + bars["low"] + bars["close"]) / 3).cumsum() / bars["volume"].cumsum()
        
        volume_distribution = bars["volume"] / bars["volume"].sum()
        order_sizes = np.round(volume_distribution * total_qty).astype(int)

        for i, row in bars.iterrows():
            if self.stop_current_trade.is_set():  # Stop execution if flagged
                logger.info(f"Stopping VWAP execution for {symbol} due to a new signal!")
                return
            trade_qty = order_sizes[i]
            if trade_qty > 0:
                self.gateway.send_trade(symbol, trade_qty, side, price=row["vwap"], type="limit")
                logger.debug(f"VWAP Order: {trade_qty} {symbol} @ VWAP ${row['vwap']:.2f}")
            time.sleep(1)

    def _execute_twap(self, symbol, total_qty, side, duration=60, interval=5):
        chunk_size = total_qty // (duration // interval)
        remaining_qty = total_qty

        for _ in range(duration // interval):
            if remaining_qty <= 0 or self.stop_current_trade.is_set():  # Stop execution if flagged
                logger.info(f"Stopping TWAP execution for {symbol} due to a new signal!")
                return

            trade_qty = min(chunk_size, remaining_qty)

            self.gateway.send_trade(symbol, trade_qty, side, price=None, type="market")
            logger.debug(f"TWAP Order: {trade_qty} {symbol}")

            remaining_qty -= trade_qty
            time.sleep(interval)
