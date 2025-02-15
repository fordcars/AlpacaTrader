import threading
import time
from datetime import datetime, timedelta, timezone

import alpaca_trade_api as tradeapi
from config import Config
from trade_book import TradeBook
from signal_stream import SignalStream

class Strategy:
    def __init__(self, config: Config):
        self.config = config
        self.trade_book = TradeBook(config)
        self.signals = SignalStream(config)
        self.start_time = datetime.now(timezone.utc)

        print("Setting up Alpaca API...")
        self.api = tradeapi.REST(
            Config.alpaca_api_key, Config.alpaca_api_secret, Config.alpaca_base_url, api_version="v2")
        
        print("Listening to order updates")
        self.order_monitor_thread = threading.Thread(target=self._monitor_order_updates, daemon=True)
        self.order_monitor_thread.start()
    
    def start(self):
        print("Starting strategy...")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        print(f"Received signal: {signal}")
        self._send_trade(
            symbol=signal["ticker"],
            qty=10,
            side="buy" if signal["direction"] == "b" else "sell",
            price=1,
            type="limit",
            time_in_force="gtc"
            )

    def _send_trade(self, symbol: str, qty: int, side: str, price,
                   type: str = "market", time_in_force: str = "gtc") -> None:
        if side == "buy":
            success = self.trade_book.send_buy(symbol, qty)
        else:
            success = self.trade_book.send_sell(symbol, qty)
        if not success:
            return
        
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=type,
                limit_price=price,
                time_in_force=time_in_force
            )
            print(f"Order submitted: Symbol={order.symbol}, Price={order.filled_avg_price}, "
                  f"Status={order.status}, Direction={order.side}")
        except Exception as e:
            print(f"Error executing trade: {e}")

    def _monitor_order_updates(self):
        processed_orders = set()  # Track processed order IDs

        while True:
            try:
                # Fetch the latest 50 closed orders (filled or canceled)
                orders = self.api.list_orders(status="closed", limit=50, after=self.start_time.isoformat())
                
                if not orders:
                    time.sleep(2)  # No new orders, wait and retry
                    continue

                # Sort orders by update time (newest first)
                orders = sorted(orders, key=lambda o: o.updated_at, reverse=True)

                for order in orders:
                    if order.id in processed_orders:
                        continue  # Skip already processed orders

                    symbol = order.symbol
                    qty = int(order.filled_qty) if order.filled_qty else 0
                    fill_price = float(order.filled_avg_price) if order.filled_avg_price else None
                    side = order.side

                    if order.status == "filled" and qty > 0:
                        if side == "buy":
                            self.trade_book.buy_filled(symbol, fill_price, qty)
                        elif side == "sell":
                            self.trade_book.sell_filled(symbol, fill_price, qty)
                        print(f"Order filled: ID={order.id}, Symbol={symbol}, Side={order.side}, "
                            f"Qty={order.filled_qty}, Price={order.filled_avg_price}, Updated={order.updated_at}")

                    elif order.status == "canceled":
                        print(f"Order canceled: ID={order.id}, Symbol={symbol}, "
                            f"Side={order.side}, Qty={order.qty}, Updated={order.updated_at}")

                        if order.side == "buy":
                            self.trade_book.send_buy(symbol, -int(order.qty))  # Reverse open exposure
                        elif order.side == "sell":
                            self.trade_book.send_sell(symbol, -int(order.qty))  # Reverse open exposure

                    # Mark order as processed
                    processed_orders.add(order.id)

                time.sleep(2)
            except Exception as e:
                print(f"Error monitoring order updates: {e}")
                time.sleep(5)
