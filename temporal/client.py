"""Temporal client helpers for the FinFlow API."""

from __future__ import annotations

from typing import Any

import structlog
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode

from core.config import get_settings
from temporal.workflows.invoice_lifecycle import ApprovalSignal, InvoiceLifecycleWorkflow

logger = structlog.get_logger(__name__)

_client: Client | None = None

INVOICE_TASK_QUEUE = "finflow-invoices"
MAINTENANCE_TASK_QUEUE = "finflow-maintenance"


def invoice_workflow_id(invoice_id: str) -> str:
    return f"invoice-{invoice_id}"


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = await Client.connect(settings.temporal_address)
    return _client


async def close_temporal_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def start_invoice_workflow(payload: dict[str, Any]) -> str:
    """Start durable invoice processing; idempotent per invoice_id."""
    client = await get_temporal_client()
    invoice_id = payload["invoice_id"]
    workflow_id = invoice_workflow_id(invoice_id)

    try:
        handle = await client.start_workflow(
            InvoiceLifecycleWorkflow.run,
            payload,
            id=workflow_id,
            task_queue=INVOICE_TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
        )
        logger.info("temporal_invoice_workflow_started", workflow_id=workflow_id)
        return handle.id
    except RPCError as exc:
        if exc.status == RPCStatusCode.ALREADY_EXISTS:
            logger.info("temporal_invoice_workflow_already_running", workflow_id=workflow_id)
            return workflow_id
        raise


async def signal_invoice_approval(
    *,
    invoice_id: str,
    decision: str,
    approver_id: str,
    notes: str = "",
    approver_role: str = "",
) -> None:
    """Send approval/rejection signal to the running invoice workflow."""
    client = await get_temporal_client()
    workflow_id = invoice_workflow_id(invoice_id)
    handle = client.get_workflow_handle(workflow_id)

    await handle.signal(
        InvoiceLifecycleWorkflow.approval_decision,
        ApprovalSignal(
            decision=decision,
            approver_id=approver_id,
            notes=notes,
            approver_role=approver_role,
        ),
    )
    logger.info(
        "temporal_approval_signal_sent",
        workflow_id=workflow_id,
        decision=decision,
        approver_id=approver_id,
    )
