"""
Redis utilities for Coordinator and Delegator.
Handles shared state, pub/sub, and status persistence.

IMPORTANT: Workers MUST NOT import this module.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Callable

try:
    import redis
    from redis.client import PubSub
except ImportError:
    raise ImportError("redis not installed. Install with: pip install redis")


logger = logging.getLogger(__name__)


def get_redis_client() -> redis.Redis:
    """
    Get or create a Redis client from REDIS_URL env var.
    
    Returns:
        Redis client instance
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url, decode_responses=True)


def write_task_status(
    request_id: str, 
    task_id: str, 
    status_dict: dict
) -> None:
    """
    Write task status to Redis hash: request:{request_id}:task:{task_id}
    
    Args:
        request_id: Unique request identifier
        task_id: Unique task identifier
        status_dict: Dictionary with fields: status, updated_at, worker_id, message
    """
    client = get_redis_client()
    key = f"request:{request_id}:task:{task_id}"
    
    # Add timestamp if not provided
    if "updated_at" not in status_dict:
        status_dict["updated_at"] = datetime.utcnow().isoformat()
    
    try:
        # Use hmset for compatibility with older Redis servers (pre-4.0)
        # client.hset(key, mapping=status_dict) relies on Redis 4.0+
        client.hmset(key, status_dict)
        logger.info(f"Wrote task status: {key} = {status_dict}")
    except Exception as e:
        logger.error(f"Failed to write task status to Redis: {e}")


def publish_status_event(request_id: str, event_dict: dict) -> None:
    """
    Publish a status event to Redis Pub/Sub channel: request:{request_id}:status
    
    Args:
        request_id: Unique request identifier
        event_dict: Event data (task_id, status, progress, message, timestamp)
    """
    client = get_redis_client()
    channel = f"request:{request_id}:status"
    
    # Ensure timestamp is in event
    if "timestamp" not in event_dict:
        event_dict["timestamp"] = datetime.utcnow().isoformat()
    
    message = json.dumps(event_dict)
    
    try:
        client.publish(channel, message)
        logger.info(f"Published to {channel}: {message}")
    except Exception as e:
        logger.error(f"Failed to publish status event to Redis: {e}")


def subscribe_to_status_events(
    request_id: str,
    callback: Callable[[dict], None],
    timeout: Optional[float] = None
) -> None:
    """
    Subscribe to status events for a request and call callback on each message.
    Blocks until timeout or manually stopped.
    
    Args:
        request_id: Unique request identifier
        callback: Function to call on each message, receives parsed event dict
        timeout: Seconds to listen before returning (None = indefinite)
    """
    client = get_redis_client()
    pubsub = client.pubsub()
    channel = f"request:{request_id}:status"
    
    try:
        pubsub.subscribe(channel)
        logger.info(f"Subscribed to {channel}")
        
        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event = json.loads(message["data"])
                    logger.info(f"Received status event: {event}")
                    callback(event)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse event message: {e}")
    except Exception as e:
        logger.error(f"Error in Redis subscription: {e}")
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
        logger.info(f"Unsubscribed from {channel}")


def read_task_status(request_id: str, task_id: str) -> Optional[dict]:
    """
    Read current task status from Redis hash.
    
    Args:
        request_id: Unique request identifier
        task_id: Unique task identifier
        
    Returns:
        Task status dict or None if not found
    """
    client = get_redis_client()
    key = f"request:{request_id}:task:{task_id}"
    
    try:
        status = client.hgetall(key)
        return status if status else None
    except Exception as e:
        logger.error(f"Failed to read task status from Redis: {e}")
        return None


def health_check() -> bool:
    """
    Check if Redis is accessible.
    
    Returns:
        True if Redis is healthy, False otherwise
    """
    try:
        client = get_redis_client()
        client.ping()
        logger.info("Redis health check passed")
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
