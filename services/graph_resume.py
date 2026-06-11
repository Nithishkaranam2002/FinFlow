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
) -> dict[str, Any]:
    from agents.graph import invoice_graph

    config = {"configurable": {"thread_id": thread_id}}
    resume_payload = {
        "decision": decision,
        "approver_id": approver_id,
        "notes": notes,
        "approver_role": approver_role,
    }

    result = await invoice_graph.ainvoke(Command(resume=resume_payload), config)
    logger.info(
        "invoice_graph_resumed",
        thread_id=thread_id,
        decision=decision,
        approver_id=approver_id,
    )
    return result
