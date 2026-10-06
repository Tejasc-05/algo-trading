"""Async Redis connection pool. Redis is used only for caching, pub/sub, and
rate limiting — PostgreSQL remains the source of truth for persistent data.
"""
from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

redis_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=5)


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=redis_pool)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()
