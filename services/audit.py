import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit import AuditLog


async def log_audit_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID,
    actor_role: str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry
