from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.tenant_context import TenantContextMiddleware
from api.routes import auth, dashboard, invoices, payments, reconciliation, vendors
from core.config import get_settings
from core.database import engine, get_db
from core.kafka import kafka_producer_manager

API_VERSION = "1.0.0"
logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
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

    yield

    await kafka_producer_manager.stop()
    await engine.dispose()
    logger.info("application_shutdown")


app = FastAPI(
    title="FinFlow API",
    version=API_VERSION,
    lifespan=lifespan,
)

settings = get_settings()
if settings.is_development:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(TenantContextMiddleware)
app.add_middleware(RequestLoggingMiddleware)
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


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        logger.exception("health_check_database_failed")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
    }
