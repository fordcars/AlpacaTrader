import redis
from config import Config

import logging
logger = logging.getLogger(__name__)

class SignalStream():
    def __init__(self, config: Config):
        self.config = config
        self.redis_client = redis.Redis(
            host="redis",
            port=config.redis_port,
            decode_responses=True
        )
        logger.info("Waiting for signals...")
        
    def get_signals(self):
        last_id = "$" # Latest message
        
        while True:
            # Read new messages from the stream
            response = self.redis_client.xread(
                {"nvda": last_id},
                block=1000
            )
            
            if response:
                # Update last_id
                for stream_name, messages in response:
                    for message_id, data in messages:
                        last_id = message_id
                        yield data