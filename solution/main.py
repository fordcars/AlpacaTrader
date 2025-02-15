from strategy import Strategy
from config import Config

def start():
    strat = Strategy(Config)
    strat.start()

if __name__ == "__main__":
    start()

def execute_trade(symbol, qty, side, type="market", time_in_force="gtc"):
    try:
        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type=type,
            time_in_force=time_in_force
        )
        print(f"Order submitted: {order}")
    except Exception as e:
        print(f"Error executing trade: {e}")

# Example trade execution (buying NVDA options - dummy example)
#execute_trade("NVDA", 1, "buy")