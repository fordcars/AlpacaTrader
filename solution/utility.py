from alpaca_api import AlpacaAPI
from alpaca.data.requests import StockLatestTradeRequest, OptionLatestTradeRequest
from alpaca.trading.enums import AssetClass

import logging
logger = logging.getLogger(__name__)

def get_asset_latest_trade(alpaca_api: AlpacaAPI, symbol: str, asset_class: AssetClass = AssetClass.US_EQUITY):
    if asset_class == AssetClass.US_EQUITY:
        try:
            request_params = StockLatestTradeRequest(symbol_or_symbols=symbol)
            return alpaca_api.hist.get_stock_latest_trade(request_params)[symbol]
        except Exception as e:
            logger.error(f"Error getting latest stock trade: {e}")
            return None
    else:
        try:
            # Option
            request_params = OptionLatestTradeRequest(symbol_or_symbols=symbol)
            return alpaca_api.opt_hist.get_option_latest_trade(request_params)[symbol]
        except Exception as e:
            logger.error(f"Error getting latest option trade: {e}")
            return None