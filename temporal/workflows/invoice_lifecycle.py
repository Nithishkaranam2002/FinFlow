"""Invoice lifecycle workflow — durable orchestration with human approval signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.invoice import (
        process_invoice_pipeline,
        resume_invoice_approval_activity,
    )


@dataclass
class ApprovalSignal:
    decision: str
    approver_id: str
    notes: str = ""
    approver_role: str = ""


def _needs_approval_wait(result: dict[str, Any]) -> bool:
    status = result.get("approval_status")
    if status == "pending":
        return True
    metadata = result.get("metadata") or {}
    return bool(metadata.get("thread_id") and status not in {"approved", "rejected"})


@workflow.defn(name="InvoiceLifecycleWorkflow")
class InvoiceLifecycleWorkflow:
    def __init__(self) -> None:
        self._approval_signal: ApprovalSignal | None = None

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await workflow.execute_activity(
            process_invoice_pipeline,
            payload,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if not _needs_approval_wait(result):
            return result

        await workflow.wait_condition(lambda: self._approval_signal is not None)

        signal = self._approval_signal
        assert signal is not None

        resume_params = {
            "thread_id": (result.get("metadata") or {}).get("thread_id")
            or payload["invoice_id"],
            "decision": signal.decision,
            "approver_id": signal.approver_id,
            "notes": signal.notes,
            "approver_role": signal.approver_role,
            "invoice_id": payload["invoice_id"],
            "tenant_id": payload["tenant_id"],
        }
        return await workflow.execute_activity(
            resume_invoice_approval_activity,
            resume_params,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    @workflow.signal
    async def approval_decision(self, signal: ApprovalSignal) -> None:
        self._approval_signal = signal
