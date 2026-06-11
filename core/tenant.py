import uuid
from contextvars import ContextVar

_current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_tenant_id",
    default=None,
)


def set_current_tenant_id(tenant_id: uuid.UUID) -> None:
    _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> uuid.UUID | None:
    return _current_tenant_id.get()


def clear_current_tenant_id() -> None:
    _current_tenant_id.set(None)
