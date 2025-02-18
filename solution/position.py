from alpaca_api import AlpacaAPI
from alpaca.data.requests import StockLatestTradeRequest, OptionLatestTradeRequest
from alpaca.trading.enums import AssetClass

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

        latest_trade = self.get_asset_latest_trade()
        self.avg_price = latest_trade.price

        logger.info(
            f"Created position for {self.symbol} ({self.asset_class}) with avg price ${self.avg_price}")

    def adjust_exposure(self, qty: int) -> None:
        self.open_orders += qty

    def get_open_exposure(self) -> float:
        return self.open_orders * self.avg_price

    def fill_position(self, fill_price: float, qty: int) -> None:
        if self.quantity == 0:
            self.avg_price = fill_price
        else:
            self.avg_price = (self.avg_price * self.quantity +
                              fill_price * qty) / (self.quantity + qty)

        self.quantity += qty
        self.open_orders -= qty  # Reduce open orders upon fill
    
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