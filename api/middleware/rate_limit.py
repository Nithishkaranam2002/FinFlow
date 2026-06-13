"""Redis-backed rate limiting for auth and general API traffic."""

from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.config import get_settings

logger = structlog.get_logger(__name__)

LOGIN_PATH = "/api/v1/auth/login"
HEALTH_PATHS = {"/health", "/live", "/ready"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled or request.url.path in HEALTH_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        is_login = request.url.path == LOGIN_PATH and request.method == "POST"
        limit = settings.login_rate_limit_per_minute if is_login else settings.api_rate_limit_per_minute
        window_key = f"ratelimit:{'login' if is_login else 'api'}:{client_ip}"

        try:
            import redis.asyncio as redis

            client = redis.from_url(settings.redis_url, socket_connect_timeout=1)
            try:
                current = await client.incr(window_key)
                if current == 1:
                    await client.expire(window_key, 60)
                if current > limit:
                    logger.warning(
                        "rate_limit_exceeded",
                        path=request.url.path,
                        client_ip=client_ip,
                        count=current,
                        limit=limit,
                    )
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please try again shortly."},
                        headers={"Retry-After": "60"},
                    )
            finally:
                await client.aclose()
        except Exception:
            logger.exception("rate_limit_check_failed")
            # Fail open so Redis outages do not take down the API.

        return await call_next(request)
