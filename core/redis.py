"""Async Redis client for caching and semantic extraction cache."""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis

from core.config import get_settings


@lru_cache
def get_redis_client() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)
