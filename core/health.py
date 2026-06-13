"""Extended health checks for production monitoring."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings

logger = structlog.get_logger(__name__)


async def check_database(db: AsyncSession) -> str:
    try:
        await db.execute(text("SELECT 1"))
        return "healthy"
    except Exception:
        logger.exception("health_check_database_failed")
        return "unhealthy"


async def check_redis() -> str:
    settings = get_settings()
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            pong = await client.ping()
            return "healthy" if pong else "unhealthy"
        finally:
            await client.aclose()
    except Exception:
        logger.exception("health_check_redis_failed")
        return "unhealthy"


async def check_qdrant() -> str:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.qdrant_url.rstrip('/')}/healthz")
            return "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        logger.exception("health_check_qdrant_failed")
        return "degraded"


async def gather_health(db: AsyncSession) -> dict[str, Any]:
    db_status, redis_status, qdrant_status = await asyncio.gather(
        check_database(db),
        check_redis(),
        check_qdrant(),
    )
    components = {
        "database": db_status,
        "redis": redis_status,
        "qdrant": qdrant_status,
    }
    overall = "healthy"
    if db_status != "healthy":
        overall = "degraded"
    elif redis_status != "healthy" or qdrant_status != "healthy":
        overall = "degraded"
    return {"status": overall, "components": components}
