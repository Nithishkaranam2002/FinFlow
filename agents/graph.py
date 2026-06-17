"""LangGraph invoice pipeline orchestration."""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.approval_agent import (
    await_approval_node,
    route_approval_node,
    send_approval_notification_node,
)
from agents.base import BaseAgent
from agents.ingestion_agent import extract_invoice_node
from agents.matching_agent import check_fraud_node, match_vendor_node
from agents.state import FinFlowState, min_confidence_score
from core.observability import trace_agent_step
from langgraph.types import interrupt

EXTRACTION_CONFIDENCE_THRESHOLD = 0.75
FRAUD_RISK_THRESHOLD = 0.7

_agent = BaseAgent()
_invoice_graph = None


def get_invoice_graph():
    """Return the compiled invoice graph (lazy init with configured checkpointer)."""
    global _invoice_graph
    if _invoice_graph is None:
        from core.checkpointer import get_checkpointer

        _invoice_graph = build_invoice_graph(get_checkpointer())
    return _invoice_graph


def reset_invoice_graph() -> None:
    """Force graph recompilation after checkpointer initialization."""
    global _invoice_graph
    _invoice_graph = None


@trace_agent_step("invoice")
async def validate_node(state: FinFlowState) -> dict:
    update = _agent.log_step(state, "validate")
    extracted = state.get("extracted_data") or {}
    missing = [
        field
        for field in ("invoice_number", "total_amount")
        if not extracted.get(field)
    ]

    if missing:
        return {
            **update,
            "requires_human_review": True,
            "review_reason": f"Missing required fields: {', '.join(missing)}",
            "error": "validation_failed",
        }

    return {**update, "requires_human_review": False, "review_reason": "", "error": ""}


@trace_agent_step("invoice")
async def human_review_node(state: FinFlowState) -> dict:
    update = _agent.log_step(state, "human_review")

    review_payload = {
        "invoice_id": state.get("invoice_id"),
        "tenant_id": state.get("tenant_id"),
        "reason": state.get("review_reason") or "Manual review required",
        "extracted_data": state.get("extracted_data"),
        "fraud_flags": state.get("fraud_flags", []),
        "overall_risk_score": state.get("overall_risk_score", 0.0),
    }
    decision = interrupt(review_payload)

    if isinstance(decision, dict):
        return {
            **update,
            "requires_human_review": False,
            "approval_notes": decision.get("approval_notes", ""),
            "metadata": {
                **(state.get("metadata") or {}),
                "human_review_decision": decision,
            },
        }

    return {
        **update,
        "requires_human_review": False,
        "approval_notes": str(decision),
    }


@trace_agent_step("invoice")
async def schedule_payment_node(state: FinFlowState) -> dict:
    from agents.payment_agent import enrich_payment_metadata_node

    memo_update = await enrich_payment_metadata_node(state)
    update = _agent.log_step(state, "schedule_payment")
    update["step_history"] = memo_update.get("step_history", []) + update.get("step_history", [])
    state = {**state, **memo_update}
    if state.get("approval_status") != "approved":
        return {
            **update,
            "error": "payment_not_scheduled",
            "review_reason": "Payment requires approved invoice",
        }

    payment_id = state.get("payment_id") or f"pay_{state['invoice_id'][:8]}"
    return {
        **update,
        "payment_id": payment_id,
        "approval_status": "approved",
        "metadata": {
            **(state.get("metadata") or {}),
            **(memo_update.get("metadata") or {}),
            "payment_scheduled": True,
        },
        "step_history": (memo_update.get("step_history") or []) + (update.get("step_history") or []),
    }


def route_at_start(state: FinFlowState) -> Literal["extract", "validate"]:
    metadata = state.get("metadata") or {}
    if metadata.get("skip_extraction"):
        return "validate"
    if state.get("extracted_data") and not state.get("raw_file_bytes"):
        return "validate"
    return "extract"


def route_after_extract(
    state: FinFlowState,
) -> Literal["validate", "human_review"]:
    if state.get("requires_human_review"):
        return "human_review"
    overall = (state.get("metadata") or {}).get("overall_confidence")
    if overall is not None and overall < EXTRACTION_CONFIDENCE_THRESHOLD:
        return "human_review"
    if min_confidence_score(state.get("confidence_scores")) < EXTRACTION_CONFIDENCE_THRESHOLD:
        return "human_review"
    return "validate"


def route_after_fraud(
    state: FinFlowState,
) -> Literal["route_approval", "human_review"]:
    """Always route matched invoices to approval policy; human review is for extraction issues."""
    return "route_approval"


def route_after_route_approval(
    state: FinFlowState,
) -> Literal["schedule_payment", "send_approval_notification"]:
    if state.get("approval_status") == "approved":
        return "schedule_payment"
    return "send_approval_notification"


def route_after_approval(
    state: FinFlowState,
) -> Literal["schedule_payment", "__end__"]:
    if state.get("approval_status") == "approved":
        return "schedule_payment"
    return "__end__"


def build_invoice_graph(checkpointer: MemorySaver | None = None):
    graph = StateGraph(FinFlowState)

    graph.add_node("extract", extract_invoice_node)
    graph.add_node("validate", validate_node)
    graph.add_node("match_vendor", match_vendor_node)
    graph.add_node("check_fraud", check_fraud_node)
    graph.add_node("route_approval", route_approval_node)
    graph.add_node("send_approval_notification", send_approval_notification_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("await_approval", await_approval_node)
    graph.add_node("schedule_payment", schedule_payment_node)

    graph.add_conditional_edges(
        START,
        route_at_start,
        {"extract": "extract", "validate": "validate"},
    )
    graph.add_conditional_edges(
        "extract",
        route_after_extract,
        {"validate": "validate", "human_review": "human_review"},
    )
    graph.add_edge("validate", "match_vendor")
    graph.add_edge("match_vendor", "check_fraud")
    graph.add_conditional_edges(
        "check_fraud",
        route_after_fraud,
        {"route_approval": "route_approval", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "route_approval",
        route_after_route_approval,
        {
            "schedule_payment": "schedule_payment",
            "send_approval_notification": "send_approval_notification",
        },
    )
    graph.add_edge("send_approval_notification", "await_approval")
    graph.add_edge("human_review", "route_approval")
    graph.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {"schedule_payment": "schedule_payment", "__end__": END},
    )
    graph.add_edge("schedule_payment", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


class _InvoiceGraphProxy:
    """Lazy proxy so importers can use `invoice_graph` after checkpointer init."""

    def __getattr__(self, name: str):
        return getattr(get_invoice_graph(), name)


invoice_graph = _InvoiceGraphProxy()
