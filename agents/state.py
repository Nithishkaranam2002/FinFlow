"""Shared agent state definition for the FinFlow LangGraph pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict


class FinFlowState(TypedDict):
    """State carried through the invoice processing graph."""

    invoice_id: str
    tenant_id: str
    raw_file_bytes: NotRequired[bytes]
    file_type: NotRequired[str]
    extracted_data: NotRequired[dict[str, Any]]
    confidence_scores: NotRequired[dict[str, float]]
    vendor_match: NotRequired[dict[str, Any] | None]
    po_match: NotRequired[dict[str, Any] | None]
    fraud_flags: NotRequired[list[dict[str, Any]]]
    overall_risk_score: NotRequired[float]
    requires_human_review: NotRequired[bool]
    review_reason: NotRequired[str]
    approval_status: NotRequired[str]
    approver_id: NotRequired[str]
    approval_notes: NotRequired[str]
    payment_id: NotRequired[str]
    error: NotRequired[str]
    step_history: Annotated[list[str], operator.add]
    metadata: NotRequired[dict[str, Any]]


def create_initial_state(
    *,
    invoice_id: str,
    tenant_id: str,
    raw_file_bytes: bytes | None = None,
    file_type: str = "pdf",
    metadata: dict[str, Any] | None = None,
) -> FinFlowState:
    """Build a fresh graph state for a new invoice run."""
    state: FinFlowState = {
        "invoice_id": invoice_id,
        "tenant_id": tenant_id,
        "step_history": [],
    }
    if raw_file_bytes is not None:
        state["raw_file_bytes"] = raw_file_bytes
    if file_type:
        state["file_type"] = file_type
    if metadata:
        state["metadata"] = metadata
    return state


def min_confidence_score(confidence_scores: dict[str, float] | None) -> float:
    """Return the lowest per-field confidence score."""
    if not confidence_scores:
        return 0.0
    return min(confidence_scores.values())
