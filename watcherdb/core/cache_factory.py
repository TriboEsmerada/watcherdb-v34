"""
Cache factory — returns RedisLikeCache or RedisAdapter based on config.

Usage:
    from watcherdb.core.cache_factory import get_cache
    cache = get_cache()
"""
import os
import logging

logger = logging.getLogger(__name__)


def get_cache(persistence_file: str = "watcherdb_cache.db", max_memory_mb: int = 100):
    """
    Return a cache instance based on USE_REDIS environment variable.

    Args:
        persistence_file: File for RedisLikeCache persistence (ignored if using Redis)
        max_memory_mb: Memory limit for cache

    Returns:
        RedisLikeCache or RedisAdapter instance
    """
    use_redis = os.getenv("USE_REDIS", "false").lower() in ("true", "1", "yes")

    if use_redis:
        try:
            from watcherdb.core.redis_adapter import RedisAdapter
            cache = RedisAdapter(max_memory_mb=max_memory_mb)
            # Verify connection
            cache.client.ping()
            logger.info("Using REAL Redis backend")
            return cache
        except Exception as e:
            logger.warning(f"Redis connection failed ({e}), falling back to in-memory cache")

    from watcherdb.core.cache import RedisLikeCache
    logger.info("Using in-memory RedisLikeCache backend")
    return RedisLikeCache(persistence_file=persistence_file, max_memory_mb=max_memory_mb)
