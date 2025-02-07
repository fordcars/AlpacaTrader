import redis
import random
import time
import datetime
import pytz
import os
from typing import Optional

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')

def is_market_hours() -> bool:
    """Check if current time is during US market hours (9:30 AM - 4:00 PM ET)"""
    et_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(et_tz)
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close

def generate_signal() -> Optional[dict]:
    """Generate a random signal for NVDA"""
    if not is_market_hours():
        return None
    
    if random.random() < 0.005:  # 0.5% chance of generating a signal
        return {
            "ticker": "NVDA",
            "direction": random.choice(["b", "s"])
        }
    return None


def main():
    # Connect to Redis
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True
    )
    
     # Delete existing stream if it exists
    redis_client.delete('nvda')
    print("Signal mock service started")
    
    while True:
        signal = generate_signal()
        if signal:
            # Add signal to Redis stream
            redis_client.xadd(
                'nvda',
                signal,
                maxlen=1000
            )
            print(f"Signal generated: {signal}")
        
        time.sleep(4.5 + random.random() * 0.5)  # Check every second with some randomness

if __name__ == "__main__":
    main()