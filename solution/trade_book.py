from config import Config
from alpaca_api import AlpacaAPI
from alpaca.data.requests import StockLatestTradeRequest, OptionLatestTradeRequest
from alpaca.trading.enums import AssetClass
from typing import Dict
import threading
import re

import logging
logger = logging.getLogger(__name__)

class Position:
    def __init__(self, alpaca_api: AlpacaAPI, symbol: str):
        self.api = alpaca_api
        self.asset_class: AssetClass = AssetClass.US_EQUITY
        self.symbol: str = symbol
        self.underlying_symbol: str = ""
        self.quantity: int = 0
        self.open_orders: int = 0  # Track open order quantity
        self.avg_price = 0

        self._init_position()
    
    def _init_position(self):
        # Get asset info
        try:
            self.api.trade.get_asset(self.symbol)
            self.asset_class = AssetClass.US_EQUITY
        except Exception as e:
            try:
                # Try option
                asset = self.api.trade.get_option_contract(self.symbol)
                self.asset_class = AssetClass.US_OPTION
                self.underlying_symbol = asset.underlying_symbol
            except Exception as e:
                logger.error(f"Error getting asset: {e}")

        if self.asset_class == AssetClass.US_EQUITY:
            try:
                request_params = StockLatestTradeRequest(symbol_or_symbols=self.symbol)
                latest_trade = self.api.hist.get_stock_latest_trade(request_params)
                self.avg_price = latest_trade[self.symbol].price
            except Exception as e:
                logger.error(f"Error getting latest stock trade: {e}")
        else:
            try:
                # Option
                request_params = OptionLatestTradeRequest(symbol_or_symbols=self.symbol)
                latest_trade = self.api.opt_hist.get_option_latest_trade(request_params)
                self.avg_price = latest_trade[self.symbol].price
            except Exception as e:
                logger.error(f"Error getting latest option trade: {e}")

        logger.info(f"Created position for {self.symbol} ({self.asset_class}) with avg price ${self.avg_price}")

    def adjust_exposure(self, qty: int) -> None:
        self.open_orders += qty

    def get_open_exposure(self) -> float:
        return self.open_orders * self.avg_price

    def fill_position(self, fill_price: float, qty: int) -> None:
        if self.quantity == 0:
            self.avg_price = fill_price
        else:
            self.avg_price = (self.avg_price * self.quantity + fill_price * qty) / (self.quantity + qty)
        
        self.quantity += qty
        self.open_orders -= qty  # Reduce open orders upon fill
    
    def __str__(self) -> str:
        return (f"{self.symbol}: {self.quantity} shares @ ${self.avg_price:.2f}, "
                f"Open Orders: {self.open_orders}, Open Exposure: ${self.get_open_exposure():.2f}")

class TradeBook:
    def __init__(self, config: Config, alpaca_api: AlpacaAPI):
        self.config = config
        self.api = alpaca_api
        self.lock = threading.Lock()
        self.positions: Dict[str, Position] = {}
        self.cash: float = 0

    def set_cash(self, cash: float):
        self.cash = cash

    def set_position(self, symbol: str, qty: int):
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)
            self.positions[symbol].quantity = qty

    def send_buy(self, symbol: str, qty: int, price: float = 0) -> bool:
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)
            pos = self.positions[symbol]
            
            # Apply risk checks
            if qty * pos.avg_price + pos.get_open_exposure() > self.config.max_open_exposure:
                logger.warning(f"Buy risk check failed: max open exposure reached: "
                      f"${qty * pos.avg_price + pos.get_open_exposure()} > ${self.config.max_open_exposure}")
                return False
            if price is not None and qty * price > self.config.max_price:
                logger.warning(f"Buy risk check failed: max order qty ($) breached: "
                      f"${qty * price} > ${self.config.max_price}")
                return False
            pos.adjust_exposure(qty)
            return True

    def send_sell(self, symbol: str, qty: int) -> bool:
        with self.lock:
            if symbol not in self.positions:
                logger.warning(f"No existing position in {symbol} to sell")
                return False
            
            position = self.positions[symbol]

            # Prevent selling if there are unfilled buy orders (wash trading)
            if position.open_orders > 0:
                logger.warning(f"Cannot sell {symbol}: Open buy orders exist ({position.open_orders} shares pending).")
                return False

            if position.quantity < qty:
                logger.warning(f"Not enough {symbol} to sell. Available: {position.quantity}, Attempted: {qty}")
                return False
            
            position.adjust_exposure(-qty)
            return True

    def fill_buy(self, symbol: str, price: float, qty: int) -> bool:
        with self.lock:
            self.cash -= price * qty
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)

            self.positions[symbol].fill_position(price, qty)
            logger.info(f"Bought {qty} {symbol} @ ${price}, New Cash Balance: ${self.cash:.2f}")
            return True

    def fill_sell(self, symbol: str, price: float, qty: int) -> bool:
        with self.lock:
            if symbol not in self.positions or self.positions[symbol].quantity < qty:
                logger.warning(f"Not enough {symbol} to sell")
                return False

            sell_value = price * qty
            self.cash += sell_value
            self.positions[symbol].fill_position(price, -qty)

            if self.positions[symbol].quantity == 0:
                del self.positions[symbol]  # Remove position if fully sold

            logger.info(f"Sold {qty} {symbol} @ ${price}, New Cash Balance: ${self.cash:.2f}")
            return True
        
    def cancel_buy(self, symbol: str, qty: int):
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)

            self.positions[symbol].adjust_exposure(-qty)
            logger.debug(f"Canceled buy for {qty} {symbol}, Open Exposure=${self.positions[symbol].get_open_exposure()}")

    def cancel_sell(self, symbol: str, qty: int):
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)

            self.positions[symbol].adjust_exposure(qty)
            logger.debug(f"Canceled sell for {qty} {symbol}, Open Exposure=${self.positions[symbol].get_open_exposure()}")

    def get_position(self, symbol: str) -> Position:
        with self.lock:
            return self.positions.get(symbol, Position(self.api, symbol))
        
    def _calculate_pnl(self) -> float:
        logger.debug("Calculating PnL...")
        total_pnl = self.cash  # Start with cash balance

        try:
            for symbol, position in self.positions.items():
                if position.asset_class == AssetClass.US_EQUITY:
                    # Stock PnL Calculation
                    latest_price = float(self.api.hist.get_stock_latest_trade(symbol)[symbol].price)
                    position_pnl = (latest_price - position.avg_price) * position.quantity
                else:
                    # Option PnL Calculation (Assumes option symbol structure like "NVDA240216P600")
                    latest_price = float(self.api.opt_hist.get_option_latest_trade(symbol)[symbol].price)
                    contracts = position.quantity
                    option_multiplier = 100  # Each contract represents 100 shares
                    position_pnl = (latest_price - position.avg_price) * contracts * option_multiplier

                total_pnl += position_pnl

                logger.info(f"{symbol}: {position.quantity} units, Avg Price: ${position.avg_price:.2f}, "
                            f"Current Price: ${latest_price:.2f}, PnL: ${position_pnl:.2f}")

        except Exception as e:
            logger.error(f"Error calculating PnL: {e}")

        return total_pnl

    def __str__(self) -> str:
        portfolio_summary = (f"\nPortfolio Summary\n----------------------"
                             f"\n Cash Balance: ${self.cash:.2f}\n")
        if not self.positions:
            portfolio_summary += "- No open positions."
        else:
            portfolio_summary += "\nOpen Positions:\n"
            for symbol, position in self.positions.items():
                portfolio_summary += f"- {position}\n"
        return portfolio_summary
