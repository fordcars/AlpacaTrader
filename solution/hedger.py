from datetime import datetime, timedelta, timezone
from config import Config
from gateway import Gateway
from alpaca_api import AlpacaAPI
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import OrderSide, OrderStatus, OrderType, ContractType

import logging
logger = logging.getLogger(__name__)

class Hedger:
    def __init__(self, config: Config, alpaca_api: AlpacaAPI, gateway: Gateway):
        self.config = config
        self.api = alpaca_api
        self.gateway = gateway

    def _get_default_expiry(self) -> str:
        today = datetime.now(timezone.utc)
        days_until_friday = (4 - today.weekday()) % 7  # 4 represents Friday (Monday=0, Sunday=6)
        next_friday = today + timedelta(days=days_until_friday)
        return next_friday.strftime("%Y-%m-%d")

    def _get_option_symbol(self, symbol: str, strike_price: float, expiry_date: str, type: ContractType) -> str:
        request_params = GetOptionContractsRequest(
            underlying_symbols=[symbol],
            expiration_date_gte=expiry_date,
            strike_price_gte=str(strike_price),
            type=type
        )
        
        contracts = self.api.trade.get_option_contracts(request_params)
        if(contracts.option_contracts):
            return contracts.option_contracts[0].symbol
        
        return None

    def hedge_with_protective_put(self, symbol, stock_qty, stock_price):
        put_strike = round(stock_price * 0.98, 2)  # Strike price ~2% below current stock price
        expiry_date = self._get_default_expiry()  # Get next available expiry date
        option_contracts = max(1, stock_qty // 100)  # 1 contract per 100 shares

        # Get the correct option symbol from Alpaca
        option_symbol = self._get_option_symbol(symbol, put_strike, expiry_date, "put")
        if not option_symbol:
            logger.error(f"Could not find matching option symbol for {symbol} (Put @ ${put_strike})")
            return
    
        # Check if we already have a protective put for this position
        try:
            self.api.trade.get_open_position(option_symbol)
            logger.info(f"Protective put already exists for {symbol} ({option_symbol}). Skipping hedge.")
            return
        except:
            pass

        # Buy the protective put
        logger.info(f"Buying {option_contracts} protective put(s): {option_symbol} @ Strike ${put_strike}, Expiry {expiry_date}")
        self.gateway.send_trade(
            symbol=option_symbol,
            qty=option_contracts,
            price=None,
            side="buy",
            type="market",
            time_in_force="gtc"
        )
