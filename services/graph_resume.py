"""Resume paused LangGraph invoice pipelines from API endpoints."""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.types import Command

logger = structlog.get_logger(__name__)


async def resume_invoice_approval(
    *,
    thread_id: str,
    decision: str,
    approver_id: str,
    notes: str = "",
    approver_role: str = "",
    invoice_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    from agents.graph import invoice_graph
    from services.invoice_approval import record_approval_decision

    config = {"configurable": {"thread_id": thread_id}}
    resume_payload = {
        "decision": decision,
        "approver_id": approver_id,
        "notes": notes,
        "approver_role": approver_role,
    }

    snapshot = await invoice_graph.aget_state(config)
    checkpoint_values = snapshot.values if snapshot else None
    if not checkpoint_values:
        resolved_invoice_id = invoice_id or thread_id
        if not tenant_id:
            raise ValueError(
                "No workflow checkpoint found for this invoice; tenant_id is required"
            )
        await record_approval_decision(
            invoice_id=resolved_invoice_id,
            tenant_id=tenant_id,
            decision=decision,
            approver_id=approver_id,
            notes=notes,
            approver_role=approver_role,
        )
        approval_status = "approved" if decision == "approved" else "rejected"
        logger.info(
            "invoice_graph_resumed_direct",
            thread_id=thread_id,
            invoice_id=resolved_invoice_id,
            decision=decision,
            approver_id=approver_id,
        )
        return {"approval_status": approval_status, "invoice_id": resolved_invoice_id}

    result = await invoice_graph.ainvoke(Command(resume=resume_payload), config)
    logger.info(
        "invoice_graph_resumed",
        thread_id=thread_id,
        decision=decision,
        approver_id=approver_id,
    )
    return result
