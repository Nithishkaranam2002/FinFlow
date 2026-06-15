"""Temporal activities for invoice processing."""

from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="process_invoice_pipeline")
async def process_invoice_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Run LangGraph invoice pipeline until completion or human-approval interrupt."""
    from services.invoice_pipeline import build_state_from_kafka_payload, run_invoice_pipeline

    state = build_state_from_kafka_payload(payload)
    return await run_invoice_pipeline(state)


@activity.defn(name="resume_invoice_approval")
async def resume_invoice_approval_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Resume LangGraph after approver decision."""
    from services.graph_resume import resume_invoice_approval

    return await resume_invoice_approval(
        thread_id=params["thread_id"],
        decision=params["decision"],
        approver_id=params["approver_id"],
        notes=params.get("notes", ""),
        approver_role=params.get("approver_role", ""),
        invoice_id=params.get("invoice_id"),
        tenant_id=params.get("tenant_id"),
    )
