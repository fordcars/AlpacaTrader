import time
import threading

import numpy as np
from config import Config
from alpaca_api import AlpacaAPI
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.data.requests import StockBarsRequest
from alpaca.trading.enums import OrderSide, OrderStatus, TimeInForce, OrderType
from alpaca.data.timeframe import TimeFrame
from gateway import Gateway
from signal_stream import SignalStream
from hedger import Hedger

from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

class Strategy:
    def __init__(self, config: Config, alpaca_api: AlpacaAPI):
        self.config = config
        self.gateway = Gateway(config, alpaca_api)
        self.signals = SignalStream(config)
        self.hedger = Hedger(config, alpaca_api, self.gateway)

        self.api = alpaca_api
        self.stop_current_trade = threading.Event()  # Event flag to stop execution
        self.execution_threads = {}  # Store running execution threads
        self.latest_prices = {}

    def start(self):
        logger.info("Starting strategy!")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        logger.info(f"Received signal: {signal}")
        symbol = signal["ticker"]
        side = OrderSide.BUY if signal["direction"] == "b" else OrderSide.SELL

        # Stop any ongoing execution for the same symbol
        if symbol in self.execution_threads:
            self._stop_execution()
            self.execution_threads[symbol].join()
            del self.execution_threads[symbol]
        self.stop_current_trade.clear()

        # Fetch latest market price for the symbol
        try:
            request_params = StockLatestTradeRequest(symbol_or_symbols=symbol)
            latest_trade = self.api.hist.get_stock_latest_trade(request_params)
            self.latest_prices[symbol] = latest_trade[symbol].price
        except Exception as e:
            logger.error(f"Error getting latest trade: {e}")

        available_cash = self.gateway.get_available_cash()

        if available_cash < self.latest_prices[symbol]:  # Avoid placing an order if we can't afford even 1 share
            logger.error("Not enough cash to buy even 1 share. Skipping trade.")
            return

        # Calculate max quantity that fits within available cash
        qty = int(available_cash / self.latest_prices[symbol])
        execution_thread = threading.Thread(target=self._execute_dynamic_trade, args=(symbol, qty, side))
        execution_thread.daemon = True  # Ensures thread exits when program stops
        execution_thread.start()
        self.execution_threads[symbol] = execution_thread

    def _stop_execution(self):
        self.stop_current_trade.set()

    def _get_bars(self, symbol, interval: TimeFrame = TimeFrame.Day, days=5):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)  # Fetch more days to account for non-trading days

        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=interval,
            start=start_date,
            end=end_date,
            feed="iex"
        )

        try:
            return self.api.hist.get_stock_bars(request_params)[symbol]

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None
    
    def _hedge_trade(self, symbol: str, trade_qty: int, side: OrderSide, price: float, type: OrderType):
        order = self.gateway.send_trade(symbol, trade_qty, side, price=price, type=type)
        if order is not None:
            self.hedger.hedge_with_protective_put(symbol, trade_qty, self.latest_prices[symbol], side)

    def _execute_dynamic_trade(self, symbol, total_qty, side):
        price = self.latest_prices[symbol]
        bars = self._get_bars(symbol, TimeFrame.Day, 5)
        volume = sum(bar.volume for bar in bars) / len(bars)

        logger.debug(f"Market Data: {symbol} Price=${price}, Daily Volume={volume}")

        # **Step 1: Small Orders (Execute Market Order)**
        if total_qty < 50:
            logger.info(f"Executing {total_qty} {symbol} at market price")
            self._hedge_trade(symbol, total_qty, side, price=None, type=OrderType.MARKET)
            return

        # **Step 2: Medium Orders (Use Limit Orders with Smart Pricing)**
        if 50 <= total_qty < 500:
            limit_price = price * 1.001 if side == "buy" else price * 0.999  # Adjust 0.1%
            logger.info(f"Placing limit order for {total_qty} {symbol} @ ${limit_price:.2f}")
            self._hedge_trade(symbol, total_qty, side, price=limit_price, type=OrderType.LIMIT)
            return

        # **Step 3: Large Orders (VWAP or TWAP Execution)**
        if total_qty >= 500:
            # TODO: If high liquidity, use VWAP
            logger.info(f"Using TWAP execution for {total_qty} {symbol}")
            self._execute_twap(symbol, total_qty, side)

    def _execute_twap(self, symbol, total_qty, side, duration=60, interval=5):
        chunk_size = total_qty // (duration // interval)
        remaining_qty = total_qty

        for _ in range(duration // interval):
            if remaining_qty <= 0 or self.stop_current_trade.is_set():  # Stop execution if flagged
                logger.info(f"Stopping TWAP execution for {symbol} due to a new signal!")
                return

            trade_qty = min(chunk_size, remaining_qty)

            self._hedge_trade(symbol, trade_qty, side, price=None, type=OrderType.MARKET)
            logger.debug(f"TWAP Order: {trade_qty} {symbol}")

            remaining_qty -= trade_qty
            time.sleep(interval)
