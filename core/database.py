from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, with_loader_criteria

from core.config import get_settings
from core.tenant import get_current_tenant_id


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


def _register_tenant_scoping() -> None:
    from models.audit import AuditLog
    from models.invoice import Invoice
    from models.payment import Payment
    from models.reconciliation import ReconciliationMatch
    from models.user import User
    from models.vendor import Vendor

    tenant_scoped_models = (
        User,
        Vendor,
        Invoice,
        Payment,
        ReconciliationMatch,
        AuditLog,
    )

    @event.listens_for(AsyncSession.sync_session_class, "do_orm_execute")
    def _apply_tenant_scope(execute_state) -> None:
        tenant_id = get_current_tenant_id()
        if tenant_id is None or not execute_state.is_select:
            return

        for model in tenant_scoped_models:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    model,
                    lambda cls: cls.tenant_id == tenant_id,
                    include_aliases=True,
                )
            )


_register_tenant_scoping()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
