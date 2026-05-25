"""
app/core/celery_app.py
──────────────────────
Celery application factory.

Configuration decisions:
- Redis as broker AND result backend (simplest setup, sufficient for our scale)
- task_acks_late=True: task only marked done AFTER successful completion
  (if worker crashes mid-task, Redis re-queues it)
- task_reject_on_worker_lost=True: paired with acks_late for crash safety
- Separate queues: "ingestion" (heavy, slow) vs "default" (light, fast)
  This prevents a big PDF upload from blocking quick tasks
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "partsmind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.ingestion_tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,   # process one task at a time per worker

    # Queues
    task_default_queue="default",
    task_routes={
        "app.tasks.ingestion_tasks.*": {"queue": "ingestion"},
    },

    # Result expiry (keep task results for 1 hour)
    result_expires=3600,

    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=10,    # seconds between retries
)
