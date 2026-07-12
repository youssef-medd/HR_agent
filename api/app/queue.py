"""Celery client for the API.

The API does not import the worker's task code — it only needs to drop a
message on the shared Redis broker addressed to a task by name. The worker
(which has `orchestrator.run_application_step` registered) picks it up.

Keeping this behind a single function makes it trivial to mock in tests.
"""

from __future__ import annotations

from typing import Any

from celery import Celery

from app.config import settings

RUN_APPLICATION_STEP = "orchestrator.run_application_step"

_celery = Celery("welyne-api", broker=settings.redis_url, backend=settings.redis_url)


def enqueue_application_step(application_id: int, event: dict[str, Any] | None = None) -> None:
    """Send the orchestrator a step for `application_id` (fire-and-forget)."""
    _celery.send_task(RUN_APPLICATION_STEP, args=[application_id, event or {}])
