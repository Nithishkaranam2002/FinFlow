"""Extraction quality scoring via Langfuse."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_factory
from core.observability import score_extraction_trace
from models.invoice import Invoice

logger = structlog.get_logger(__name__)

SCORE_PENDING_HOURS = 24


def _extraction_flags(invoice: Invoice) -> dict[str, Any]:
    return dict(invoice.flags or {})


async def log_human_correction_score(
    *,
    invoice: Invoice,
    corrected_fields: list[str],
    corrections: dict[str, Any],
) -> None:
    flags = _extraction_flags(invoice)
    trace_id = flags.get("langfuse_trace_id")
    if not trace_id:
        logger.warning("langfuse_score_missing_trace", invoice_id=str(invoice.id))
        return

    comment = "human_corrected: " + ", ".join(corrected_fields)
    score_extraction_trace(
        trace_id=trace_id,
        value=0.0,
        comment=comment,
        metadata={"corrections": corrections, "invoice_id": str(invoice.id)},
    )
    flags["extraction_scored"] = True
    flags["extraction_corrected"] = True
    flags["extraction_scored_at"] = datetime.now(timezone.utc).isoformat()
    invoice.flags = flags


async def log_no_correction_needed_score(invoice: Invoice) -> bool:
    flags = _extraction_flags(invoice)
    if flags.get("extraction_scored") or flags.get("extraction_corrected"):
        return False

    trace_id = flags.get("langfuse_trace_id")
    if not trace_id:
        return False

    score_extraction_trace(
        trace_id=trace_id,
        value=1.0,
        comment="no_correction_needed",
        metadata={"invoice_id": str(invoice.id)},
    )
    flags["extraction_scored"] = True
    flags["extraction_scored_at"] = datetime.now(timezone.utc).isoformat()
    invoice.flags = flags
    return True


async def run_pending_extraction_quality_scores() -> dict[str, Any]:
    """Score extractions with no human correction after 24 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SCORE_PENDING_HOURS)
    scored_ids: list[str] = []

    async with async_session_factory() as db:
        result = await db.execute(select(Invoice))
        invoices = result.scalars().all()

        for invoice in invoices:
            flags = _extraction_flags(invoice)
            if flags.get("extraction_scored") or flags.get("extraction_corrected"):
                continue
            if not flags.get("langfuse_trace_id"):
                continue

            completed_raw = flags.get("extraction_completed_at")
            if not completed_raw:
                continue
            completed_at = datetime.fromisoformat(completed_raw)
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            if completed_at > cutoff:
                continue

            if await log_no_correction_needed_score(invoice):
                scored_ids.append(str(invoice.id))

        await db.commit()

    logger.info("extraction_quality_scores_applied", count=len(scored_ids))
    return {"scored_invoice_ids": scored_ids, "count": len(scored_ids)}


async def persist_extraction_trace_metadata(
    db: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    tenant_id: uuid.UUID,
    trace_id: str | None,
    observation_id: str | None,
) -> None:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        return

    invoice.flags = {
        **(invoice.flags or {}),
        "langfuse_trace_id": trace_id,
        "langfuse_extraction_observation_id": observation_id,
        "extraction_completed_at": datetime.now(timezone.utc).isoformat(),
        "extraction_scored": False,
        "extraction_corrected": False,
    }
    await db.flush()
