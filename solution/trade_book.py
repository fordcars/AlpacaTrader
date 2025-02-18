from datetime import datetime
from config import Config
from position import Position
from alpaca_api import AlpacaAPI
from alpaca.trading.client import Order
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.enums import AssetClass, ContractType, OrderSide
from typing import Dict
import utility
import threading

import logging
logger = logging.getLogger(__name__)


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

    def risk_check(self, side: OrderSide, symbol: str, qty: int, price: float = 0) -> bool:
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)
            pos = self.positions[symbol]

        if side == OrderSide.BUY:
            if qty * pos.avg_price + pos.get_open_exposure() > self.config.max_open_exposure:
                logger.warning(f"Buy risk check failed: max open exposure reached: "
                               f"${qty * pos.avg_price + pos.get_open_exposure()} > ${self.config.max_open_exposure}")
                return False
            if price is not None and qty * price > self.config.max_price:
                logger.warning(f"Buy risk check failed: max order qty ($) breached: "
                               f"${qty * price} > ${self.config.max_price}")
                return False
        else:
            # Prevent selling if there are unfilled buy orders (wash trading)
            if pos.open_exposure > 0:
                logger.warning(
                    f"Cannot sell {symbol}: Open buy orders exist ({pos.open_exposure} shares pending).")
                return False
        return True

    def submit_order(self, order: Order):
        with self.lock:
            self.positions[order.symbol].submit_order(order)

    def fill_buy(self, order: Order):
        with self.lock:
            self.cash -= order.filled_avg_price * order.qty
            if order.symbol not in self.positions:
                self.positions[order.symbol] = Position(self.api, order.symbol)

            self.positions[order.symbol].fill_order(order)
            logger.debug(
                f"Bought {order.qty} {order.symbol} @ ${order.price}, New Cash Balance: ${self.cash:.2f}")

    def fill_sell(self, order: Order):
        with self.lock:
            self.cash += order.filled_avg_price * order.qty
            if order.symbol not in self.positions:
                self.positions[order.symbol] = Position(self.api, order.symbol)

            self.positions[order.symbol].fill_order(order)
            logger.debug(
                f"Sold {order.qty} {order.symbol} @ ${order.price}, New Cash Balance: ${self.cash:.2f}")
            return True

    def cancel_order(self, order: Order):
        with self.lock:
            if order.symbol in self.positions:
                self.positions[order.symbol].cancel_order(order)
                logger.info(
                    f"Canceled order for {order.qty} {order.symbol}, Open Exposure=${self.positions[order.symbol].get_open_exposure()}")

    def get_position(self, symbol: str) -> Position:
        with self.lock:
            return self.positions.get(symbol, Position(self.api, symbol))

    def calculate_pnl(self) -> float:
        with self.lock:
            logger.debug("Calculating PnL...")
            total_pnl = self.cash  # Start with cash balance

            try:
                for symbol, position in self.positions.items():
                    if position.asset_class == AssetClass.US_EQUITY:
                        # Stock PnL Calculation
                        latest_price = float(utility.get_asset_latest_trade(
                            self.api, position.symbol, position.asset_class).price)
                        
                        # Handle long and short positions
                        if position.quantity > 0:  # Long position
                            position_pnl = (latest_price - position.avg_price) * position.quantity
                        else:  # Short position
                            position_pnl = (position.avg_price - latest_price) * abs(position.quantity)

                        logger.debug(f"{symbol}: {position.quantity} units, Avg Price: ${position.avg_price:.2f}, "
                                    f"Current Price: ${latest_price:.2f}, PnL: ${position_pnl:.2f}")
                    else:
                        # Option PnL Calculation
                        position_pnl = self._calculate_option_pnl(
                            symbol, position)

                    total_pnl += position_pnl

            except Exception as e:
                logger.error(f"Error calculating PnL: {e}")

            return total_pnl

    def _calculate_option_pnl(self, symbol: str, position: Position) -> float:
        try:
            asset = self.api.trade.get_option_contract(symbol)
        except Exception as e:
            logger.error(f"Error getting option contract: {e}")
            return 0.0

        latest_price = float(utility.get_asset_latest_trade(
            self.api, position.symbol, position.asset_class).price)  # Current option price
        underlying_price = float(utility.get_asset_latest_trade(
            self.api, position.underlying_symbol, AssetClass.US_EQUITY).price)  # Current stock price
        is_expired = datetime.now().date() >= asset.expiration_date

        if is_expired:
            # Calculate intrinsic value at expiry
            if asset.type == ContractType.CALL:
                option_value = max(underlying_price -
                                   float(asset.strike_price), 0) * 100
            else:
                option_value = max(
                    float(asset.strike_price) - underlying_price, 0) * 100
        else:
            # Use current market value of the option before expiry
            option_value = latest_price * 100

        pnl = (option_value - position.avg_price * 100) * position.quantity
        logger.debug(f"{symbol}: {position.quantity} units, Avg Price: ${position.avg_price}, "
                     f"Current Price: ${latest_price}, Underlying: ${underlying_price}, PnL: ${pnl:.2f}")
        return pnl

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
