"""Run the LangGraph invoice pipeline from Kafka payloads or existing invoices."""

from __future__ import annotations

import base64
from typing import Any

import structlog

from agents.graph import invoice_graph
from agents.state import FinFlowState, create_initial_state
from models.invoice import Invoice
from services.invoice_documents import load_invoice_bytes

logger = structlog.get_logger(__name__)


def build_state_from_kafka_payload(payload: dict[str, Any]) -> FinFlowState:
    content_type = payload.get("content_type", "application/pdf")
    file_type = "pdf" if "pdf" in content_type else "png"
    raw_bytes = load_invoice_bytes(
        storage_key=payload.get("storage_key"),
        file_base64=payload.get("file_base64"),
    )
    return create_initial_state(
        invoice_id=str(payload["invoice_id"]),
        tenant_id=str(payload["tenant_id"]),
        raw_file_bytes=raw_bytes,
        file_type=file_type,
        metadata=payload,
    )


def build_state_from_invoice(invoice: Invoice, *, skip_extraction: bool = True) -> FinFlowState:
    flags = invoice.flags or {}
    metadata = {
        "skip_extraction": skip_extraction,
        "overall_confidence": invoice.extraction_confidence,
        "vendor_id": str(invoice.vendor_id),
        "thread_id": str(invoice.id),
    }
    return {
        "invoice_id": str(invoice.id),
        "tenant_id": str(invoice.tenant_id),
        "extracted_data": invoice.extracted_data or {},
        "confidence_scores": flags.get("confidence_scores") or {},
        "requires_human_review": False,
        "review_reason": "",
        "fraud_flags": [],
        "overall_risk_score": 0.0,
        "metadata": metadata,
        "step_history": [],
    }


async def run_invoice_pipeline(state: FinFlowState) -> dict[str, Any]:
    """Execute the invoice graph; pauses at await_approval when human sign-off is required."""
    config = {"configurable": {"thread_id": state["invoice_id"]}}
    result = await invoice_graph.ainvoke(state, config)
    logger.info(
        "invoice_pipeline_completed",
        invoice_id=state["invoice_id"],
        approval_status=result.get("approval_status"),
        steps=result.get("step_history"),
    )
    return result
