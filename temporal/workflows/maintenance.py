"""Scheduled maintenance workflows (replaces Celery beat)."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.maintenance import (
        recover_stale_invoices,
        run_approval_escalation,
        run_extraction_quality_scores,
    )


@workflow.defn(name="ApprovalEscalationWorkflow")
class ApprovalEscalationWorkflow:
    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            run_approval_escalation,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


@workflow.defn(name="StaleInvoiceRecoveryWorkflow")
class StaleInvoiceRecoveryWorkflow:
    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            recover_stale_invoices,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


@workflow.defn(name="ExtractionQualityWorkflow")
class ExtractionQualityWorkflow:
    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            run_extraction_quality_scores,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
