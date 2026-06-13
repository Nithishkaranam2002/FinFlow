from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

import structlog
from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import register_exception_handlers
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.middleware.tenant_context import TenantContextMiddleware
from api.routes import auth, dashboard, invoices, payments, reconciliation, vendors
from core.checkpointer import close_checkpointer, init_checkpointer
from core.config import get_settings
from core.database import engine, get_db
from core.health import gather_health
from core.kafka import kafka_producer_manager

API_VERSION = "1.0.0"
logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger.info("application_starting", app=settings.app_name, env=settings.app_env)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("database_connection_ok")
    except Exception:
        logger.exception("database_connection_failed")
        raise

    try:
        await kafka_producer_manager.start()
    except Exception:
        logger.warning("kafka_producer_unavailable", exc_info=True)

    try:
        await init_checkpointer()
        from agents.graph import reset_invoice_graph as _reset_graph

        _reset_graph()
    except Exception:
        logger.exception("checkpointer_init_failed")
        if settings.is_production:
            raise

    yield

    await kafka_producer_manager.stop()
    await close_checkpointer()
    await engine.dispose()
    logger.info("application_shutdown")


settings = get_settings()

app = FastAPI(
    title="FinFlow API",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

register_exception_handlers(app)

if settings.is_development:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

app.add_middleware(TenantContextMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(invoices.router, prefix="/api/v1/invoices", tags=["invoices"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
app.include_router(
    reconciliation.router,
    prefix="/api/v1/reconciliation",
    tags=["reconciliation"],
)
app.include_router(vendors.router, prefix="/api/v1/vendors", tags=["vendors"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])


@app.get("/live")
async def liveness_probe() -> dict:
    return {"status": "alive", "version": API_VERSION}


@app.get("/ready")
async def readiness_probe(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await gather_health(db)
    payload = {
        **result,
        "version": API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.app_env,
    }
    code = status.HTTP_200_OK if result["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=payload)


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    result = await gather_health(db)
    return {
        **result,
        "version": API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.app_env,
    }
