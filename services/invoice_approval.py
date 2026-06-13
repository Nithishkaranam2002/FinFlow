"""Persist invoice approval decisions when the LangGraph checkpoint is unavailable."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from core.database import async_session_factory
from core.tenant import set_current_tenant_id
from models.invoice import Invoice, InvoiceStatus
from services.audit import log_audit_event

logger = structlog.get_logger(__name__)


async def record_approval_decision(
    *,
    invoice_id: str,
    tenant_id: str,
    decision: str,
    approver_id: str,
    notes: str = "",
    approver_role: str = "",
) -> InvoiceStatus:
    """Apply an approval or rejection directly to the invoice record."""
    if decision not in {"approved", "rejected"}:
        raise ValueError(f"Invalid approval decision: {decision}")

    approval_status = "approved" if decision == "approved" else "rejected"
    invoice_status = (
        InvoiceStatus.APPROVED
        if approval_status == "approved"
        else InvoiceStatus.REJECTED
    )

    async with async_session_factory() as db:
        set_current_tenant_id(uuid.UUID(tenant_id))
        result = await db.execute(
            select(Invoice).where(
                Invoice.id == uuid.UUID(invoice_id),
                Invoice.tenant_id == uuid.UUID(tenant_id),
            )
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise ValueError(f"Invoice not found: {invoice_id}")

        old_status = invoice.status.value
        invoice.status = invoice_status
        invoice.flags = {
            **(invoice.flags or {}),
            "approver_id": approver_id,
            "approval_notes": notes,
            "approval_decision_at": datetime.now(timezone.utc).isoformat(),
        }

        await log_audit_event(
            db,
            tenant_id=uuid.UUID(tenant_id),
            entity_type="invoice",
            entity_id=uuid.UUID(invoice_id),
            action=f"approval_{decision}",
            actor_id=uuid.UUID(approver_id),
            actor_role=approver_role or (invoice.flags or {}).get("required_role", "approver"),
            old_value={"status": old_status},
            new_value={
                "status": invoice_status.value,
                "approval_status": approval_status,
                "approver_id": approver_id,
            },
            reason=notes or None,
        )
        await db.commit()

    logger.info(
        "approval_decision_recorded",
        invoice_id=invoice_id,
        decision=decision,
        approver_id=approver_id,
        via="direct",
    )
    return invoice_status
