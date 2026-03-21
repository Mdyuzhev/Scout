"""Redis connection singleton for Scout streaming."""
from __future__ import annotations

import os
from loguru import logger

_redis = None


async def get_redis():
    """Get or create async Redis connection."""
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        url = os.getenv("REDIS_URL", "redis://scout-redis:6379/0")
        _redis = aioredis.from_url(url, decode_responses=True)
        logger.info("Redis connected: {}", url)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
