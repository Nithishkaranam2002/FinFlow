"""Temporal activities replacing former Celery maintenance tasks."""

from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="run_approval_escalation")
async def run_approval_escalation() -> dict[str, Any]:
    from agents.approval_agent import escalation_check_node

    return await escalation_check_node()


@activity.defn(name="recover_stale_invoices")
async def recover_stale_invoices() -> dict[str, Any]:
    from temporal.activities.stale_recovery import recover_stale_invoices_impl

    return await recover_stale_invoices_impl()


@activity.defn(name="run_extraction_quality_scores")
async def run_extraction_quality_scores() -> dict[str, Any]:
    from services.extraction_quality import run_pending_extraction_quality_scores

    return await run_pending_extraction_quality_scores()
