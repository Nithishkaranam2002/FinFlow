"""Global API exception handlers."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.config import get_settings

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    settings = get_settings()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
        )
        detail = str(exc) if settings.debug else "An unexpected error occurred"
        return JSONResponse(status_code=500, content={"detail": detail})
