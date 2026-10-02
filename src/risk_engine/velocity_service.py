import time
from typing import Optional

import redis

from src.common.config import settings
from src.common.logger import get_logger

logger = get_logger("velocity_service")


class VelocityService:
    """
    Sub-millisecond sliding window velocity tracking using Redis Sorted Sets (ZADD / ZREMRANGEBYSCORE).
    """

    def __init__(
        self, host: Optional[str] = None, port: Optional[int] = None, password: Optional[str] = None
    ):
        self.host = host or settings.REDIS_HOST
        self.port = port or settings.REDIS_PORT
        self.password = password or settings.REDIS_PASSWORD
        self._client: Optional[redis.Redis] = None

    def get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        return self._client

    def record_and_get_velocity(
        self, entity_key: str, window_seconds: int = 300, amount: float = 0.0
    ) -> int:
        """
        Records a transaction timestamp into Redis sorted set and returns count within window_seconds.
        """
        now = time.time()
        window_start = now - window_seconds
        key = f"vel:{entity_key}"

        try:
            r = self.get_client()
            pipe = r.pipeline()
            # Remove timestamps older than window
            pipe.zremrangebyscore(key, 0, window_start)
            # Add current timestamp
            member = f"{now}:{amount}:{time.time_ns()}"
            pipe.zadd(key, {member: now})
            # Count elements in current window
            pipe.zcard(key)
            # Set TTL to ensure memory cleanup
            pipe.expire(key, window_seconds * 2)
            results = pipe.execute()
            count = results[2]
            return int(count)
        except Exception as e:
            logger.warning(f"Redis velocity tracking error for {entity_key}: {e}")
            return 1  # Safe fallback

    def get_blacklist_match(self, entity_type: str, entity_value: str) -> bool:
        """
        Checks if entity is in Redis hot blacklist cache.
        """
        if not entity_value:
            return False
        try:
            r = self.get_client()
            return bool(r.sismember(f"blacklist:{entity_type.upper()}", entity_value))
        except Exception as e:
            logger.warning(f"Redis blacklist lookup error: {e}")
            return False
