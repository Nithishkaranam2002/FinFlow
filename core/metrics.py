"""Prometheus metrics for HTTP request monitoring."""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "finflow_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "finflow_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        REQUEST_LATENCY.labels(request.method, path).observe(duration)
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        return response


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), "text/plain; version=0.0.4; charset=utf-8"
