import redis
import time

def test_stream():
    redis_client = redis.Redis(
        host='redis',
        port=6379,
        decode_responses=True
    )
    
    print("Waiting for signals...")
    
    # Get the latest entry ID or use '0' if none exists
    last_id = '0'
    
    while True:
        # Read new messages from the stream
        response = redis_client.xread(
            {'nvda': last_id},
            block=1000
        )
        
        if response:
            # Update last_id and print new messages
            for stream_name, messages in response:
                for message_id, data in messages:
                    last_id = message_id
                    print(f"Received signal: {data}")
        
        time.sleep(0.1)

if __name__ == "__main__":
    test_stream()