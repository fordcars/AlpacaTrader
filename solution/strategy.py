from config import Config
from gateway import Gateway
from signal_stream import SignalStream

class Strategy:
    def __init__(self, config: Config):
        self.config = config
        self.gateway = Gateway(config)
        self.signals = SignalStream(config)
    
    def start(self):
        print("Starting strategy...")
        for signal in self.signals.get_signals():
            self._handle_signal(signal)

    def _handle_signal(self, signal):
        print(f"Received signal: {signal}")
        self.gateway.send_trade(
            symbol=signal["ticker"],
            qty=10,
            side="buy" if signal["direction"] == "b" else "sell",
            price=1000,
            type="limit",
            time_in_force="gtc"
            )
