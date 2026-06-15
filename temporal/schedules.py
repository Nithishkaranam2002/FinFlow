"""Register Temporal schedules (replaces Celery beat)."""

from __future__ import annotations

import structlog
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
)
from temporalio.service import RPCError, RPCStatusCode

from temporal.client import MAINTENANCE_TASK_QUEUE
from temporal.workflows.maintenance import (
    ApprovalEscalationWorkflow,
    ExtractionQualityWorkflow,
    StaleInvoiceRecoveryWorkflow,
)

logger = structlog.get_logger(__name__)

SCHEDULES: list[tuple[str, object, ScheduleSpec]] = [
    (
        "finflow-approval-escalation",
        ApprovalEscalationWorkflow.run,
        ScheduleSpec(intervals=[ScheduleIntervalSpec(every_hours=1)]),
    ),
    (
        "finflow-stale-invoice-recovery",
        StaleInvoiceRecoveryWorkflow.run,
        ScheduleSpec(intervals=[ScheduleIntervalSpec(every_minutes=15)]),
    ),
    (
        "finflow-extraction-quality",
        ExtractionQualityWorkflow.run,
        ScheduleSpec(intervals=[ScheduleIntervalSpec(every_hours=1)]),
    ),
]


def _build_schedule(workflow_run: object, spec: ScheduleSpec) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            workflow_run,
            task_queue=MAINTENANCE_TASK_QUEUE,
        ),
        spec=spec,
        state=ScheduleState(note="FinFlow maintenance"),
    )


async def ensure_schedules(client: Client) -> None:
    for schedule_id, workflow_run, spec in SCHEDULES:
        schedule = _build_schedule(workflow_run, spec)
        try:
            handle = client.get_schedule_handle(schedule_id)
            await handle.update(lambda _: ScheduleUpdate(schedule=schedule))
            logger.info("temporal_schedule_updated", schedule_id=schedule_id)
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                logger.exception("temporal_schedule_update_failed", schedule_id=schedule_id)
                raise
            await client.create_schedule(schedule_id, schedule)
            logger.info("temporal_schedule_created", schedule_id=schedule_id)
