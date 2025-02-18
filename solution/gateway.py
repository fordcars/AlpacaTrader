import threading
import time

from alpaca.trading.client import GetOrdersRequest
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce, OrderType, OrderStatus
from config import Config
from alpaca_api import AlpacaAPI
from trade_book import TradeBook
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

class Gateway:
    def __init__(self, config: Config, alpaca_api: AlpacaAPI):
        self.config = config
        self.recover_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.start_time = datetime.now()
        
        self.api = alpaca_api
        self.trade_book = TradeBook(config, alpaca_api)
        self._recover_trade_state()

        self.order_monitor_thread = threading.Thread(target=self._monitor_order_updates, daemon=True)
        self.order_monitor_thread.start()
        self._start_pnl_monitor()

    def _recover_trade_state(self):
        logger.info(f"Recovering trade state since {self.recover_time.isoformat()}")
        self._recover_positions()
        self._recover_open_orders()
        logger.info(str(self.trade_book))

    def _recover_positions(self):
        try:
            positions = self.api.trade.get_all_positions()
            self.trade_book.set_cash(float(self.api.trade.get_account().cash))
            logger.info(f"Recovering {len(positions)} position(s)...")
            
            for pos in positions:
                self.trade_book.set_position(pos.symbol, int(pos.qty), float(pos.avg_entry_price))
                
                logger.debug(f"Recovered position: {pos.symbol} - {pos.qty} shares")
        except Exception as e:
            logger.error(f"Error recovering positions: {e}")

    def _recover_open_orders(self):
        processed_orders = set()

        try:
            orders_request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                after=self.recover_time,
                limit=500
            )
            orders = self.api.trade.get_orders(filter=orders_request)

            # Sort orders by update time (newest first)
            orders = sorted(orders, key=lambda o: o.updated_at, reverse=True)
            logger.info(f"Recovering {len(orders)} open order(s)...")

            for order in orders:
                if order.id in processed_orders:
                    continue  # Skip already processed orders

                if order.side == OrderSide.BUY:
                    logger.debug(f"Applying buy order: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
                elif order.side == OrderSide.SELL:
                    logger.debug(f"Applying sell order: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
                self.trade_book.submit_order(order)

                # Mark order as processed
                processed_orders.add(order.id)
        except Exception as e:
            logger.error(f"Error recovering open orders: {e}")

    def _monitor_order_updates(self):
        logger.info("Listening to order updates...")
        processed_orders = set()

        while True:
            try:
                # Fetch both filled and canceled orders
                orders_request = GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    after=self.start_time,
                    limit=50
                )
                orders = self.api.trade.get_orders(filter=orders_request)

                if not orders:
                    time.sleep(2)  # No new orders, wait and retry
                    continue

                # Sort orders by update time (newest first)
                orders = sorted(orders, key=lambda o: o.updated_at, reverse=True)

                for order in orders:
                    if order.id in processed_orders:
                        continue  # Skip already processed orders

                    qty = int(order.filled_qty) if order.filled_qty else 0

                    if order.status == OrderStatus.FILLED and qty > 0:
                        if order.side == OrderSide.BUY:
                            self.trade_book.fill_buy(order)
                        elif order.side == OrderSide.SELL:
                            self.trade_book.fill_sell(order)
                        logger.info(f"Order filled: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")

                    elif order.status == OrderStatus.CANCELED:
                        logger.info(f"Order canceled: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
                        self.trade_book.cancel_order(order)

                    # Mark order as processed
                    processed_orders.add(order.id)

                time.sleep(2)
            except Exception as e:
                logger.error(f"Error monitoring order updates: {e}")
                time.sleep(5)

    def _start_pnl_monitor(self):
        def pnl_monitor():
            while True:
                pnl = self.trade_book.calculate_pnl()
                logger.info(f"Current PnL: ${pnl:.2f}")
                time.sleep(30)
        
        pnl_thread = threading.Thread(target=pnl_monitor, daemon=True)
        pnl_thread.start()

    def get_available_cash(self):
        return self.trade_book.cash

    def send_trade(self, symbol: str, qty: int, side: OrderSide, price,
                   type: OrderType = OrderType.MARKET, time_in_force: TimeInForce = TimeInForce.GTC):
        logger.debug(f"Attempting to send trade: Symbol={symbol}, Qty={qty}, "
                  f"Price={price}, Type={type}")
        if not self.trade_book.risk_check(side, symbol, qty, price):
            return None
        
        if type == OrderType.MARKET:
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=time_in_force
            )
        elif type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit orders require a price.")
            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                limit_price=price,
                time_in_force=time_in_force
            )
        else:
            raise ValueError(f"Unsupported order type: {type}")
        
        try:
            order = self.api.trade.submit_order(order_request)
            self.trade_book.submit_order(order)
            logger.info(f"Order submitted: ID={order.id}, Symbol={order.symbol}, Side={order.side}, "
                            f"Qty={order.qty}, Price={order.limit_price}, Updated={order.updated_at}")
            return order
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            return None
