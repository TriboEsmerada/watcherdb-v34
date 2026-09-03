"""
Redis adapter — same interface as RedisLikeCache but backed by real Redis.

Usage:
    from watcherdb.core.cache_factory import get_cache
    cache = get_cache()  # Returns RedisLikeCache or RedisAdapter based on USE_REDIS
"""
import os
import time
import logging
import json
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)


class RedisAdapter:
    """Real Redis backend with the same interface as RedisLikeCache."""

    def __init__(self, host: str = None, port: int = None, db: int = 0, max_memory_mb: int = 256):
        import redis
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db
        self.client = redis.Redis(
            host=self.host, port=self.port, db=self.db,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.stats = {
            'hits': 0, 'misses': 0, 'sets': 0,
            'deletes': 0, 'expired': 0,
        }
        # Set memory limit
        try:
            self.client.config_set("maxmemory", f"{max_memory_mb}mb")
            self.client.config_set("maxmemory-policy", "allkeys-lru")
        except Exception:
            pass  # May not have CONFIG SET permission
        logger.info(f"RedisAdapter connected to {self.host}:{self.port}/{self.db}")

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                self.client.setex(key, ttl, serialized)
            else:
                self.client.set(key, serialized)
            self.stats['sets'] += 1
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self.client.get(key)
            if raw is None:
                self.stats['misses'] += 1
                return None
            self.stats['hits'] += 1
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            self.stats['misses'] += 1
            return None

    def delete(self, key: str) -> bool:
        try:
            result = self.client.delete(key)
            if result:
                self.stats['deletes'] += 1
            return bool(result)
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        try:
            return bool(self.client.exists(key))
        except Exception:
            return False

    def keys(self, pattern: str = "*") -> List[str]:
        try:
            return list(self.client.keys(pattern))
        except Exception:
            return []

    def flushall(self) -> bool:
        try:
            self.client.flushdb()
            return True
        except Exception:
            return False

    def ttl(self, key: str) -> int:
        try:
            return self.client.ttl(key)
        except Exception:
            return -2

    def incr(self, key: str, amount: int = 1) -> int:
        try:
            return self.client.incr(key, amount)
        except Exception:
            return 0

    def expire(self, key: str, ttl: int) -> bool:
        try:
            return bool(self.client.expire(key, ttl))
        except Exception:
            return False

    def publish(self, channel: str, message: Any) -> int:
        try:
            serialized = json.dumps(message, default=str)
            return self.client.publish(channel, serialized)
        except Exception:
            return 0

    def subscribe(self, channel: str, callback: Callable):
        self.subscribers[channel].append(callback)

    def get_stats(self) -> dict:
        try:
            info = self.client.info("memory")
            return {
                **self.stats,
                'backend': 'redis',
                'memory_used': info.get('used_memory_human', 'N/A'),
                'connected_clients': self.client.info("clients").get('connected_clients', 0),
                'total_keys': self.client.dbsize(),
            }
        except Exception:
            return {**self.stats, 'backend': 'redis', 'status': 'error'}

    def shutdown(self):
        try:
            self.client.close()
        except Exception:
            pass
