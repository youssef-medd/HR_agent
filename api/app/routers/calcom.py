"""Cal.com booking webhook.

Real A6 confirmation channel. The booking link A6 sends carries the application
id as booking metadata (`?metadata[application_id]=…`); when the candidate books
a slot, Cal.com POSTs a `BOOKING_CREATED` event here. We map it back to the
paused application (state PRESCREENED) and resume the orchestrator with a
natural-language confirmation — the same event shape the stub reply endpoint
sends — so the existing schedule node interprets it and advances to
INTERVIEW_SCHEDULED. Always returns 200 so Cal.com does not retry.

When `CALCOM_WEBHOOK_SECRET` is set, the `X-Cal-Signature-256` header (HMAC-SHA256
of the raw body) is verified.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.interviews import InterviewError, book_slot, cancel, parse_slot, reschedule
from app.models.application import Application
from app.queue import enqueue_application_step

router = APIRouter(prefix="/webhooks/calcom", tags=["webhooks"])

# Cal.com trigger events we act on. Everything else (payment, meeting-ended,
# form submissions) is acknowledged and dropped.
_HANDLED = {"BOOKING_CREATED", "BOOKING_RESCHEDULED", "BOOKING_CANCELLED"}


def _signature_ok(raw: bytes, header: str | None) -> bool:
    secret = settings.calcom_webhook_secret
    if not secret:
        return True  # verification disabled
    if not header:
        return False
    sig = header.split("=", 1)[1] if header.startswith("sha256=") else header
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _application_id(payload: dict[str, Any]) -> int | None:
    meta = payload.get("metadata") or {}
    raw = meta.get("application_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@router.post("")
async def receive(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_cal_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    raw = await request.body()
    if not _signature_ok(raw, x_cal_signature_256):
        return {"status": "ignored"}

    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        return {"status": "ignored"}

    event = body.get("triggerEvent")
    if event not in _HANDLED:
        return {"status": "ignored"}

    payload = body.get("payload") or {}
    app_id = _application_id(payload)
    if app_id is None:
        return {"status": "ignored"}

    row = db.get(Application, app_id)
    if row is None:
        return {"status": "ignored"}

    start_time = payload.get("startTime")

    if event == "BOOKING_CREATED":
        if row.state != "PRESCREENED":
            return {"status": "ignored"}
        # Persist the concrete start time so the schedule node + reminder job
        # have a real datetime anchor (the resume message is only free text).
        if start_time:
            try:
                book_slot(db, row, start=parse_slot(str(start_time)), source="calcom")
            except ValueError:
                pass
        when = start_time or "the scheduled time"
        enqueue_application_step(
            app_id, {"candidate_message": f"I booked the interview for {when} via Cal.com."}
        )
        return {"status": "ok"}

    # Replan / cancellation of an already booked interview. By now the graph is
    # parked on the A7 offer gate, so these are row-level lifecycle changes
    # rather than a graph resume.
    if row.state != "INTERVIEW_SCHEDULED":
        return {"status": "ignored"}

    try:
        if event == "BOOKING_RESCHEDULED":
            if not start_time:
                return {"status": "ignored"}
            reschedule(
                db, row, start=parse_slot(str(start_time)), source="calcom",
                reason=payload.get("rescheduleReason") or None,
            )
        else:  # BOOKING_CANCELLED
            cancel(db, row, source="calcom", reason=payload.get("cancellationReason") or None)
    except (ValueError, InterviewError):
        return {"status": "ignored"}
    return {"status": "ok"}
