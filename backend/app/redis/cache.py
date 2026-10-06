"""Small helpers over the raw Redis client: JSON get/set and a fixed-window
counter used by the auth rate limiter. Nothing here is a source of truth —
every value is disposable/derivable and may have a TTL.
"""
import json
from typing import Any

import redis.asyncio as redis


async def cache_get_json(client: redis.Redis, key: str) -> Any | None:
    raw = await client.get(key)
    return json.loads(raw) if raw is not None else None


async def cache_set_json(client: redis.Redis, key: str, value: Any, ttl_seconds: int | None = None) -> None:
    await client.set(key, json.dumps(value), ex=ttl_seconds)


async def increment_with_expiry(client: redis.Redis, key: str, ttl_seconds: int) -> int:
    """Fixed-window counter: increments `key` and sets its TTL only on the
    first increment of the window, returning the new count."""
    async with client.pipeline(transaction=True) as pipeline:
        pipeline.incr(key)
        pipeline.expire(key, ttl_seconds, nx=True)
        count, _ = await pipeline.execute()
    return count
