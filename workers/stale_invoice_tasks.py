"""Recover invoices stuck in received/extracting states."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from core.celery_app import celery_app
from core.config import get_settings
from core.database import async_session_factory
from core.kafka import TOPIC_INVOICE_RECEIVED, kafka_producer_manager
from models.invoice import Invoice, InvoiceStatus
from services.audit import log_audit_event
from services.invoice_documents import build_invoice_kafka_payload, load_invoice_bytes

logger = structlog.get_logger(__name__)
SYSTEM_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _recover_stale_invoices() -> dict:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stale_invoice_minutes)
    recovered = 0
    failed = 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.status.in_([InvoiceStatus.RECEIVED, InvoiceStatus.EXTRACTING]),
                Invoice.updated_at < cutoff,
            )
        )
        stale_invoices = result.scalars().all()

    if not stale_invoices:
        return {"recovered": 0, "failed": 0, "scanned": 0}

    if not kafka_producer_manager.is_started:
        await kafka_producer_manager.start()

    for invoice in stale_invoices:
        flags = invoice.flags or {}
        storage_key = flags.get("storage_key")
        file_b64 = flags.get("file_base64")
        if not storage_key and not file_b64:
            async with async_session_factory() as session:
                db_invoice = await session.get(Invoice, invoice.id)
                if db_invoice is None:
                    continue
                db_invoice.status = InvoiceStatus.REVIEW_REQUIRED
                db_invoice.flags = {
                    **(db_invoice.flags or {}),
                    "stale_recovery": "missing_upload_payload",
                }
                await log_audit_event(
                    session,
                    tenant_id=db_invoice.tenant_id,
                    entity_type="invoice",
                    entity_id=db_invoice.id,
                    action="stale_invoice_failed",
                    actor_id=SYSTEM_ACTOR_ID,
                    actor_role="system",
                    reason="Missing upload payload for recovery",
                    new_value={"status": InvoiceStatus.REVIEW_REQUIRED.value},
                )
                await session.commit()
            failed += 1
            continue

        try:
            load_invoice_bytes(storage_key=storage_key, file_base64=file_b64)
            payload = build_invoice_kafka_payload(
                invoice_id=invoice.id,
                tenant_id=invoice.tenant_id,
                vendor_id=invoice.vendor_id,
                filename=flags.get("upload_filename", "invoice.pdf"),
                content_type=flags.get("upload_content_type", "application/pdf"),
                storage_key=storage_key or "",
                uploaded_by=SYSTEM_ACTOR_ID,
                recovery=True,
            )
            if not storage_key:
                payload["file_base64"] = file_b64
            await kafka_producer_manager.send(
                TOPIC_INVOICE_RECEIVED,
                payload,
                key=str(invoice.id),
            )
            async with async_session_factory() as session:
                db_invoice = await session.get(Invoice, invoice.id)
                if db_invoice is None:
                    continue
                db_invoice.status = InvoiceStatus.RECEIVED
                db_invoice.flags = {
                    **(db_invoice.flags or {}),
                    "stale_recovery": datetime.now(timezone.utc).isoformat(),
                }
                await log_audit_event(
                    session,
                    tenant_id=db_invoice.tenant_id,
                    entity_type="invoice",
                    entity_id=db_invoice.id,
                    action="stale_invoice_requeued",
                    actor_id=SYSTEM_ACTOR_ID,
                    actor_role="system",
                    reason=f"Stale for over {settings.stale_invoice_minutes} minutes",
                    new_value={"status": InvoiceStatus.RECEIVED.value},
                )
                await session.commit()
            recovered += 1
        except Exception:
            logger.exception("stale_invoice_recovery_failed", invoice_id=str(invoice.id))
            failed += 1

    logger.info(
        "stale_invoice_recovery_complete",
        scanned=len(stale_invoices),
        recovered=recovered,
        failed=failed,
    )
    return {"recovered": recovered, "failed": failed, "scanned": len(stale_invoices)}


@celery_app.task(name="workers.stale_invoice_tasks.recover_stale_invoices")
def recover_stale_invoices() -> dict:
    return asyncio.run(_recover_stale_invoices())
