"""Start invoice Temporal workflows from the API."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.service import RPCError

from core.config import get_settings
from models.invoice import Invoice, InvoiceStatus
from services.graph_resume import resume_invoice_approval
from temporal.client import signal_invoice_approval, start_invoice_workflow

logger = structlog.get_logger(__name__)


async def dispatch_invoice_processing(payload: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.temporal_enabled:
        raise RuntimeError("Temporal is disabled but no fallback is configured")

    await start_invoice_workflow(payload)


async def submit_approval_decision(
    *,
    db: AsyncSession,
    invoice: Invoice,
    decision: str,
    approver_id: str,
    notes: str,
    approver_role: str,
) -> None:
    """Signal Temporal workflow; fall back to direct graph resume if workflow is absent."""
    thread_id = (invoice.flags or {}).get("thread_id", str(invoice.id))
    invoice_id = str(invoice.id)
    tenant_id = str(invoice.tenant_id)

    try:
        await signal_invoice_approval(
            invoice_id=invoice_id,
            decision=decision,
            approver_id=approver_id,
            notes=notes,
            approver_role=approver_role,
        )
        for _ in range(40):
            await asyncio.sleep(0.25)
            await db.refresh(invoice)
            if invoice.status in {
                InvoiceStatus.APPROVED,
                InvoiceStatus.REJECTED,
                InvoiceStatus.PAID,
            }:
                return
        logger.warning("temporal_approval_poll_timeout", invoice_id=invoice_id)
    except RPCError:
        logger.warning("temporal_workflow_not_found_fallback", invoice_id=invoice_id)
        await resume_invoice_approval(
            thread_id=thread_id,
            decision=decision,
            approver_id=approver_id,
            notes=notes,
            approver_role=approver_role,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
        )
    except Exception:
        logger.exception("temporal_approval_signal_failed", invoice_id=invoice_id)
        await resume_invoice_approval(
            thread_id=thread_id,
            decision=decision,
            approver_id=approver_id,
            notes=notes,
            approver_role=approver_role,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
        )
