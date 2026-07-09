"""Celery application.

Broker + backend = Redis. Same instance already declared in the compose file.
The orchestrator is a single supervisor task; concurrency is controlled at
the worker level via `--concurrency=N`.
"""

from __future__ import annotations

from celery import Celery

from orchestrator.config import settings

celery = Celery(
    "welyne-orchestrator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["orchestrator.tasks"],
)

celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=5,
    task_default_max_retries=3,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
