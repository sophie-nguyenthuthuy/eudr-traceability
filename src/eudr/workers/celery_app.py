"""Celery application factory."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from eudr.config import get_settings

settings = get_settings()

celery_app = Celery(
    "eudr",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["eudr.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=200,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "recheck-plots-weekly": {
        "task": "eudr.workers.tasks.recheck_all_plots",
        "schedule": crontab(hour=2, minute=0, day_of_week=1),
    },
}
