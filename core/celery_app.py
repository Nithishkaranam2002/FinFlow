"""Celery application and scheduled tasks."""

from celery import Celery
from celery.schedules import crontab

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "finflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "approval-escalation-hourly": {
        "task": "workers.approval_tasks.run_escalation_check",
        "schedule": crontab(minute=0),
    },
}

celery_app.autodiscover_tasks(["workers"])
