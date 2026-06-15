#!/usr/bin/env python3
"""Temporal worker for invoice workflows and scheduled maintenance."""

from __future__ import annotations

import asyncio
import sys

import structlog
from temporalio.worker import Worker

from temporal.activities.invoice import (
    process_invoice_pipeline,
    resume_invoice_approval_activity,
)
from temporal.activities.maintenance import (
    recover_stale_invoices,
    run_approval_escalation,
    run_extraction_quality_scores,
)
from temporal.client import INVOICE_TASK_QUEUE, MAINTENANCE_TASK_QUEUE, get_temporal_client
from temporal.schedules import ensure_schedules
from temporal.workflows.invoice_lifecycle import InvoiceLifecycleWorkflow
from temporal.workflows.maintenance import (
    ApprovalEscalationWorkflow,
    ExtractionQualityWorkflow,
    StaleInvoiceRecoveryWorkflow,
)

logger = structlog.get_logger(__name__)


async def run_temporal_worker() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

    try:
        from core.checkpointer import init_checkpointer
        from agents.graph import reset_invoice_graph

        await init_checkpointer()
        reset_invoice_graph()
    except Exception:
        logger.exception("temporal_worker_checkpointer_init_failed")

    client = await get_temporal_client()
    await ensure_schedules(client)

    invoice_worker = Worker(
        client,
        task_queue=INVOICE_TASK_QUEUE,
        workflows=[InvoiceLifecycleWorkflow],
        activities=[process_invoice_pipeline, resume_invoice_approval_activity],
    )
    maintenance_worker = Worker(
        client,
        task_queue=MAINTENANCE_TASK_QUEUE,
        workflows=[
            ApprovalEscalationWorkflow,
            StaleInvoiceRecoveryWorkflow,
            ExtractionQualityWorkflow,
        ],
        activities=[
            run_approval_escalation,
            recover_stale_invoices,
            run_extraction_quality_scores,
        ],
    )

    logger.info(
        "temporal_worker_started",
        invoice_queue=INVOICE_TASK_QUEUE,
        maintenance_queue=MAINTENANCE_TASK_QUEUE,
    )
    await asyncio.gather(invoice_worker.run(), maintenance_worker.run())


def main() -> None:
    try:
        asyncio.run(run_temporal_worker())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
