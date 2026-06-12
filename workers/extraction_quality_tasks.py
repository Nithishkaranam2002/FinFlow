"""Celery tasks for extraction quality scoring."""

from __future__ import annotations

import asyncio

from core.celery_app import celery_app


@celery_app.task(name="workers.extraction_quality_tasks.run_extraction_quality_scores")
def run_extraction_quality_scores() -> dict:
    from services.extraction_quality import run_pending_extraction_quality_scores

    return asyncio.run(run_pending_extraction_quality_scores())
