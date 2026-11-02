"""Optional outbound webhook fired when an invoice is fully approved (APPROVAL_WEBHOOK_URL)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from core.config import get_settings
from core.database import async_session_factory
from models.invoice import Invoice
from models.user import User
from models.vendor import Vendor

logger = structlog.get_logger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 3.0
_pending_tasks: set[asyncio.Task[None]] = set()


async def _build_payload(
    *, invoice_id: str, tenant_id: str, approver_id: str | None, approver_role: str, approved_at: str
) -> dict[str, Any] | None:
    async with async_session_factory() as db:
        invoice = (
            await db.execute(
                select(Invoice).where(
                    Invoice.id == uuid.UUID(invoice_id),
                    Invoice.tenant_id == uuid.UUID(tenant_id),
                )
            )
        ).scalar_one_or_none()
        if invoice is None:
            return None
        vendor = await db.get(Vendor, invoice.vendor_id)
        approver = await db.get(User, uuid.UUID(approver_id)) if approver_id else None

    extracted = invoice.extracted_data or {}
    return {
        "event": "invoice.approved",
        "invoice_id": str(invoice.id),
        "tenant_id": str(invoice.tenant_id),
        "vendor": {
            "id": str(invoice.vendor_id),
            "name": vendor.name if vendor else extracted.get("vendor_name"),
            "email": vendor.email if vendor else extracted.get("vendor_email"),
        },
        "invoice_number": invoice.invoice_number,
        "invoice_date": extracted.get("invoice_date"),
        "due_date": invoice.due_date.isoformat() if invoice.due_date else extracted.get("due_date"),
        "currency": invoice.currency,
        "subtotal": extracted.get("subtotal"),
        "tax_amount": extracted.get("tax_amount"),
        "total": str(invoice.amount),
        "line_items": invoice.line_items or [],
        "approved_by": {
            "id": approver_id,
            "email": approver.email if approver else None,
            "role": approver_role,
        },
        "approved_at": approved_at,
    }


async def send_approval_webhook(
    *, invoice_id: str, tenant_id: str, approver_id: str | None, approver_role: str, approved_at: str
) -> None:
    """POST the approved invoice to APPROVAL_WEBHOOK_URL. Never raises."""
    url = get_settings().approval_webhook_url
    if not url:
        return
    try:
        payload = await _build_payload(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            approver_id=approver_id,
            approver_role=approver_role,
            approved_at=approved_at,
        )
        if payload is None:
            logger.warning("approval_webhook_invoice_not_found", invoice_id=invoice_id)
            return
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info(
            "approval_webhook_sent",
            invoice_id=invoice_id,
            status_code=response.status_code,
            response=response.text[:500],
        )
    except Exception as exc:
        logger.warning("approval_webhook_failed", invoice_id=invoice_id, error=repr(exc))


def schedule_approval_webhook(
    *, invoice_id: str, tenant_id: str, approver_id: str | None, approver_role: str, approved_at: str
) -> None:
    """Fire the webhook in the background so approvals never wait on or fail because of it."""
    if not get_settings().approval_webhook_url:
        return
    try:
        task = asyncio.get_running_loop().create_task(
            send_approval_webhook(
                invoice_id=invoice_id,
                tenant_id=tenant_id,
                approver_id=approver_id,
                approver_role=approver_role,
                approved_at=approved_at,
            )
        )
        _pending_tasks.add(task)
        task.add_done_callback(_pending_tasks.discard)
    except Exception as exc:
        logger.warning("approval_webhook_schedule_failed", invoice_id=invoice_id, error=repr(exc))
