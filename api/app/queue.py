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
SEND_PORTAL_LINK = "orchestrator.send_portal_link"
SEND_INTERVIEW_UPDATE = "orchestrator.send_interview_update"

_celery = Celery("welyne-api", broker=settings.redis_url, backend=settings.redis_url)


def enqueue_application_step(application_id: int, event: dict[str, Any] | None = None) -> None:
    """Send the orchestrator a step for `application_id` (fire-and-forget)."""
    _celery.send_task(RUN_APPLICATION_STEP, args=[application_id, event or {}])


def enqueue_interview_update(application_id: int, kind: str) -> None:
    """Ask the worker to send an A6 interview update (reschedule / cancel / no-show).

    The DB write already happened in the API (it owns the row); only the
    candidate-facing message — which needs SMTP and the ICS builder — is handed
    to the worker.
    """
    _celery.send_task(SEND_INTERVIEW_UPDATE, args=[application_id, kind])


def enqueue_portal_link(email: str, links: list[dict[str, str]]) -> None:
    """Ask the worker to email a candidate their signed portal links.

    SMTP lives in the worker with every other outbound message, so the API mints
    the tokens (it owns `JWT_SECRET`) and hands over rendered title/url pairs.
    """
    _celery.send_task(SEND_PORTAL_LINK, args=[email, links])
