from config import Config
from typing import Dict
import threading

class Position:
    def __init__(self, alpaca_api, symbol: str):
        self.symbol: str = symbol
        self.quantity: int = 0
        self.avg_price: float = alpaca_api.get_latest_trade(symbol).price
        self.open_orders: int = 0  # Track open order quantity
        print(f"Created position for {self.symbol} with avg price ${self.avg_price}")

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
    def __init__(self, config: Config, alpaca_api):
        self.config = config
        self.api = alpaca_api
        self.lock = threading.Lock()
        self.positions: Dict[str, Position] = {}
        self.cash: float = config.starting_cash

    def send_buy(self, symbol: str, qty: int, price: float = 0) -> bool:
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)
            pos = self.positions[symbol]
            
            # Apply risk checks
            if qty * pos.avg_price + pos.get_open_exposure() > self.config.max_open_exposure:
                print(f"Buy risk check failed: max open exposure reached: "
                      f"${qty * pos.avg_price + pos.get_open_exposure()} > ${self.config.max_open_exposure}")
                return False
            if qty * price > self.config.max_price:
                print(f"Buy risk check failed: max order qty ($) breached: "
                      f"${qty * price} > ${self.config.max_price}")
                return False
            pos.adjust_exposure(qty)
            return True

    def send_sell(self, symbol: str, qty: int, price: float = 0) -> bool:
        with self.lock:
            if symbol not in self.positions:
                print(f"No existing position in {symbol} to sell")
                return False
            
            position = self.positions[symbol]

            # Prevent selling if there are unfilled buy orders (wash trading)
            if position.open_orders > 0:
                print(f"Cannot sell {symbol}: Open buy orders exist ({position.open_orders} shares pending).")
                return False

            if position.quantity < qty:
                print(f"Not enough {symbol} to sell. Available: {position.quantity}, Attempted: {qty}")
                return False
            
            position.adjust_exposure(-qty)
            return True

    def fill_buy(self, symbol: str, price: float, qty: int) -> bool:
        with self.lock:
            self.cash -= price * qty
            if symbol not in self.positions:
                self.positions[symbol] = Position(self.api, symbol)

            self.positions[symbol].fill_position(price, qty)
            print(f"Bought {qty} {symbol} @ ${price}, New Cash Balance: ${self.cash:.2f}")
            return True

    def fill_sell(self, symbol: str, price: float, qty: int) -> bool:
        with self.lock:
            if symbol not in self.positions or self.positions[symbol].quantity < qty:
                print(f"Not enough {symbol} to sell")
                return False

            sell_value = price * qty
            self.cash += sell_value
            self.positions[symbol].fill_position(price, -qty)

            if self.positions[symbol].quantity == 0:
                del self.positions[symbol]  # Remove position if fully sold

            print(f"Sold {qty} {symbol} @ ${price}, New Cash Balance: ${self.cash:.2f}")
            return True

    def get_position(self, symbol: str) -> Position:
        with self.lock:
            return self.positions.get(symbol, Position(self.api, symbol))

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
