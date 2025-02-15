from config import Config
from typing import Dict
import threading

class Position:
    def __init__(self, symbol: str):
        self.symbol: str = symbol
        self.quantity: int = 0
        self.avg_price: float = 0.0 # Will be set after first fill (use MD instead?)
        self.open_orders: int = 0  # Track open order quantity

    def adjust_exposure(self, qty: int) -> None:
        self.open_orders += qty

    def fill_position(self, fill_price: float, qty: int) -> None:
        if self.quantity == 0:
            self.avg_price = fill_price
        else:
            self.avg_price = (self.avg_price * self.quantity + fill_price * qty) / (self.quantity + qty)
        
        self.quantity += qty
        self.open_orders -= qty  # Reduce open orders upon fill
        
    def get_open_exposure(self) -> float:
        return self.open_orders * self.avg_price
    
    def __str__(self) -> str:
        return (f"{self.symbol}: {self.quantity} shares @ ${self.avg_price:.2f}, "
                f"Open Orders: {self.open_orders}, Open Exposure: ${self.get_open_exposure():.2f}")

class TradeBook:
    def __init__(self, config: Config):
        self.lock = threading.Lock()
        self.positions: Dict[str, Position] = {}
        self.cash: float = config.starting_cash

    def send_buy(self, symbol: str, qty: int) -> bool:
        with self.lock:
            if symbol not in self.positions:
                self.positions[symbol] = Position(symbol)
            
            self.positions[symbol].adjust_exposure(qty)
            return True

    def send_sell(self, symbol: str, qty: int) -> bool:
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

    def buy_filled(self, symbol: str, price: float, qty: int) -> bool:
        with self.lock:
            self.cash -= price * qty
            if symbol not in self.positions:
                self.positions[symbol] = Position(symbol)

            self.positions[symbol].fill_position(price, qty)
            print(f"Bought {qty} {symbol} @ ${price}, New Cash Balance: ${self.cash:.2f}")
            return True

    def sell_filled(self, symbol: str, price: float, qty: int) -> bool:
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
            return self.positions.get(symbol, Position(symbol))

    def __str__(self) -> str:
        portfolio_summary = (f"\nPortfolio Summary\n----------------------"
                             f"\n Cash Balance: ${self.cash:.2f}\n")
        if not self.positions:
            portfolio_summary += "🔹 No open positions."
        else:
            portfolio_summary += "\nOpen Positions:\n"
            for symbol, position in self.positions.items():
                portfolio_summary += f"🔹 {position}\n"
        return portfolio_summary
