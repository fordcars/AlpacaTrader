import threading

import numpy as np
from config import Config
import utility
from alpaca_api import AlpacaAPI
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.data.requests import StockBarsRequest
from alpaca.trading.enums import OrderSide, AssetClass, OrderType
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
        self.latest_prices = {}
        self.traded_symbols = [
            "NVDA",
            "AMD",
            "QQQ",
            "SMH"
        ]

    def start(self):
        logger.info("Starting strategy!")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        logger.info(f"Received signal: {signal}")
        symbol = signal["ticker"]
        side = OrderSide.BUY if signal["direction"] == "b" else OrderSide.SELL

        for symbol in self.traded_symbols:
            self.latest_prices[symbol] = float(utility.get_asset_latest_trade(
                self.api, symbol, AssetClass.US_EQUITY).price)

        self.execute_trade(side)

    def _get_bars(self, symbol, interval: TimeFrame = TimeFrame.Day, days=5):
        end_date = datetime.now()
        # Fetch more days to account for non-trading days
        start_date = end_date - timedelta(days=days * 2)

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
        order = self.gateway.send_trade(
            symbol, trade_qty, side, price=price, type=type)
        if order is not None:
            self.hedger.hedge_with_protective_put(
                symbol, trade_qty, self.latest_prices[symbol], side)

    def execute_trade(self, side: OrderSide):
        available_cash = self.gateway.get_available_cash()

        # Define allocations
        allocations = {
            "NVDA": 0.60,  # 60% NVDA
            "AMD":  0.20,  # 20% AMD
            "QQQ":  0.10,  # 10% QQQ
            "SMH":  0.10   # 10% SMH
        }

        # Execute Market Orders for NVDA and AMD (immediate exposure)
        for symbol, weight in allocations.items():
            allocation = available_cash * weight
            latest_price = self.latest_prices[symbol]
            qty = int(allocation / latest_price)
            if qty < 1:
                logger.debug(f"Skipping trade, target qty for {symbol} is 0")
                continue

            if symbol in ["NVDA", "AMD"]:
                # Use Market Order for quick execution
                self._hedge_trade(symbol, qty, side,
                                  price=None, type=OrderType.MARKET)
            else:
                # Use Limit Order for better price
                limit_price = round(latest_price * 1.001, 2)  # 0.1% higher to increase fill probability
                self._hedge_trade(symbol, qty, side,
                                  price=limit_price, type=OrderType.LIMIT)
