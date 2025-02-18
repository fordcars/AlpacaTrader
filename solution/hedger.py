from datetime import datetime, timedelta
from config import Config

import logging
logger = logging.getLogger(__name__)

class Hedger:
    def __init__(self, config: Config, alpaca_api):
        self.config = config
        self.api = alpaca_api

    def _get_default_expiry(self):
        """ Returns the next Friday expiry date for options. """
        today = datetime.today()
        days_until_friday = (4 - today.weekday()) % 7  # Friday is weekday 4
        expiry = today + timedelta(days=days_until_friday)
        return expiry

    def _get_open_positions(self, symbol):
        positions = self.api.list_positions()
        return [p for p in positions if p.symbol == symbol]

    def _get_option_symbol(self, stock_symbol, strike_price, expiry_date, option_type):
        # Format expiry date (convert YYYY-MM-DD to YYMMDD)
        expiry_str = expiry_date.strftime("%y%m%d")

        # Option type format ("P" for Put, "C" for Call)
        option_code = "P" if option_type.lower() == "put" else "C"

        # Format strike price (Alpaca symbols often use no decimal)
        strike_price_str = f"{int(strike_price * 1000):05d}".lstrip("0")

        # Construct the expected option symbol
        option_symbol = f"{stock_symbol}{expiry_str}{option_code}{strike_price_str}"

        # Verify the symbol exists
        try:
            assets = self.api.list_assets()
            available_symbols = {asset.symbol for asset in assets}

            if option_symbol in available_symbols:
                return option_symbol
            else:
                logger.error(f"Option symbol {option_symbol} not found in Alpaca assets!")
                return None
        except Exception as e:
            logger.error(f"Error getting option symbol: {e}")
    
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
        existing_puts = self._get_open_positions(option_symbol)
        if existing_puts:
            logger.info(f"Protective put already exists for {symbol} ({option_symbol}). Skipping hedge.")
            return

        # Buy the protective put
        logger.info(f"Buying {option_contracts} protective put(s): {option_symbol} @ Strike ${put_strike}, Expiry {expiry_date}")
        self.gateway.send_trade(
            symbol=option_symbol,
            qty=option_contracts,
            side="buy",
            type="market",
            time_in_force="gtc"
        )
