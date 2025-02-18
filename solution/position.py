from alpaca_api import AlpacaAPI
from alpaca.trading.client import Order
from alpaca.data.requests import StockLatestTradeRequest, OptionLatestTradeRequest
from alpaca.trading.enums import AssetClass, OrderSide

import logging
logger = logging.getLogger(__name__)

class Position:
    def __init__(self, alpaca_api: AlpacaAPI, symbol: str):
        self.api = alpaca_api
        self.open_orders: dict[str, Order] = [] # Open orders for this position
        self.asset_class: AssetClass = AssetClass.US_EQUITY
        self.symbol: str = symbol
        self.underlying_symbol: str = ""
        self.quantity: int = 0
        self.avg_price = 0
        self.open_exposure: int = 0 # Open orders' total qty

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

        latest_trade = self.get_asset_latest_trade()
        self.avg_price = latest_trade.price

        logger.info(
            f"Created position for {self.symbol} ({self.asset_class}) with avg price ${self.avg_price}")

    def get_open_exposure(self) -> float:
        return self.open_exposure * self.avg_price
    
    def submit_order(self, order: Order):
        self.open_orders[order.client_order_id] = order
        if order.side == OrderSide.BUY:
            self.open_exposure += float(order.qty)

    def fill_order(self, order: Order):
        if self.quantity == 0:
            self.avg_price = float(order.filled_avg_price)
        else:
            self.avg_price = (self.avg_price * self.quantity +
                              order.filled_avg_price * float(order.filled_qty)) / (self.quantity + float(order.filled_qty))
        
        # Determine expected price (for market orders, assume latest price)
        expected_price = float(order.limit_price) if order.limit_price else self.get_asset_latest_trade().price
        actual_price = float(order.filled_avg_price)

        # Calculate slippage percentage
        slippage = ((actual_price - expected_price) / expected_price) * 100

        self.quantity += float(order.filled_qty)
        if order.side == OrderSide.BUY:
            self.open_exposure -= float(order.filled_qty)

        if order.client_order_id in self.open_orders:
            open_order = self.open_orders[order.client_order_id]
            open_order.filled_qty = float(open_order.filled_qty) + float(order.filled_qty)

            if open_order.filled_qty == float(open_order.qty):
                logger.info(f"Open order fully filled: {order} | Slippage: {slippage:.2f}%")
                self.open_orders.pop(order.client_order_id)
            else:
                fill_ratio = open_order.filled_qty/float(open_order.qty)
                logger.info(f"Open order partially filled: {order.client_order_id}, "
                        f"Fill Ratio={fill_ratio:.2f} | Slippage: {slippage:.2f}%")
        else:
            logger.warning(f"Received fill for unknown order: {order}")
    
    # Assumes full cancellation
    def cancel_order(self, order: Order):
        if order.client_order_id in self.open_orders:
            if order.side == OrderSide.BUY:
                self.open_exposure -= float(order.qty)
            logger.debug(f"Canceled order: {order}")
            self.open_orders.pop(order.client_order_id)
        else:
            logger.warning(f"Received cancel for unknown order: {order}")
    
    def get_asset_latest_trade(self):
        if self.asset_class == AssetClass.US_EQUITY:
            try:
                request_params = StockLatestTradeRequest(symbol_or_symbols=self.symbol)
                return self.api.hist.get_stock_latest_trade(request_params)[self.symbol]
            except Exception as e:
                logger.error(f"Error getting latest stock trade: {e}")
                return None
        else:
            try:
                # Option
                request_params = OptionLatestTradeRequest(symbol_or_symbols=self.symbol)
                return self.api.opt_hist.get_option_latest_trade(request_params)[self.symbol]
            except Exception as e:
                logger.error(f"Error getting latest option trade: {e}")
                return None

    def __str__(self) -> str:
        return (f"{self.symbol}: {self.quantity} shares @ ${self.avg_price:.2f}, "
                f"Open Orders: {self.open_orders}, Open Exposure: ${self.get_open_exposure():.2f}")