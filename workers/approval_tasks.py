"""Celery tasks for approval workflow maintenance."""

from __future__ import annotations

import asyncio

from core.celery_app import celery_app


@celery_app.task(name="workers.approval_tasks.run_escalation_check")
def run_escalation_check() -> dict:
    from agents.approval_agent import escalation_check_node

    return asyncio.run(escalation_check_node())
