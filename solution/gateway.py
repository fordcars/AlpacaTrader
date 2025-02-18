import threading
import time
import alpaca_trade_api as tradeapi

from config import Config
from trade_book import TradeBook
from datetime import datetime, timezone

class Gateway:
    def __init__(self, config: Config):
        self.config = config
        self.start_time = datetime.now().replace(hour=9).astimezone(timezone.utc)

        print("Setting up Alpaca API...")
        self.api = tradeapi.REST(
            config.alpaca_api_key, config.alpaca_api_secret, config.alpaca_base_url, api_version="v2")
        
        self.trade_book = TradeBook(config, self.api)
        self._recover_open_orders()
        self.order_monitor_thread = threading.Thread(target=self._monitor_order_updates, daemon=True)
        self.order_monitor_thread.start()

    def _recover_open_orders(self):
        print("Recovering open orders...")
        processed_orders = set()

        try:
            orders = self.api.list_orders(status="open", limit=500, after=self.start_time.isoformat())

            # Sort orders by update time (newest first)
            orders = sorted(orders, key=lambda o: o.updated_at, reverse=True)

            for order in orders:
                if order.id in processed_orders:
                    continue  # Skip already processed orders

                if order.side == "buy":
                    print(f"Applying buy order: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
                    self.trade_book.send_buy(order.symbol, int(order.qty), int(order.limit_price) if order.limit_price else None)
                elif order.side == "sell":
                    print(f"Applying sell order: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
                    self.trade_book.send_sell(order.symbol, int(order.qty))

                # Mark order as processed
                processed_orders.add(order.id)
        except Exception as e:
            print(f"Error recovering open orders: {e}")

    def _monitor_order_updates(self):
        print("Listening to order updates...")
        processed_orders = set()

        while True:
            try:
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
                            self.trade_book.fill_buy(symbol, fill_price, qty)
                        elif side == "sell":
                            self.trade_book.fill_sell(symbol, fill_price, qty)
                        print(f"Order filled: ID={order.id}, Symbol={symbol}, Side={order.side}, "
                            f"Qty={order.filled_qty}, Price={order.filled_avg_price}, Updated={order.updated_at}")

                    elif order.status == "canceled":
                        print(f"Order canceled: ID={order.id}, Symbol={symbol}, "
                            f"Side={order.side}, Qty={order.qty}, Updated={order.updated_at}")

                        if order.side == "buy":
                            self.trade_book.fill_buy(symbol, -int(order.qty))  # Reverse open exposure
                        elif order.side == "sell":
                            self.trade_book.fill_sell(symbol, -int(order.qty))  # Reverse open exposure

                    # Mark order as processed
                    processed_orders.add(order.id)

                time.sleep(2)
            except Exception as e:
                print(f"Error monitoring order updates: {e}")
                time.sleep(5)

    def send_trade(self, symbol: str, qty: int, side: str, price,
                   type: str = "market", time_in_force: str = "gtc") -> None:
        if side == "buy":
            success = self.trade_book.send_buy(symbol, qty, price)
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