"""A7 — outbound message logging + per-candidate rate limiting.

Writes to `message_log` from an independent session (the same durability reason
as `nodes._save_payload_key`: a node may `interrupt()` right after a send, which
discards the node session's work). The rate-limiter reads the same table.

Rate policy (spec §6 A7): at most one *notification-class* message per recipient
per window (default 4h). Interactive messages (the pre-screening Q&A, the
booking-link prompt) and application confirmations are exempt — throttling those
would break the conversation. Only the templates in `_RATE_LIMITED_TEMPLATES`
are counted, so an offer sent to a phone that also received chat messages is not
falsely suppressed.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.models.application import Application
from app.models.message_log import MessageLog
from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestrator.emails import normalize_lang

# Templates subject to the anti-spam limiter. Confirmations and interactive
# (prescreen_question / booking_link) sends are deliberately absent.
_RATE_LIMITED_TEMPLATES = {"rejection", "offer", "prescreen_invite"}


def candidate_language(db: Session, application_id: int) -> str:
    """The candidate's preferred correspondence language ('en'/'fr').

    Read from the application payload (`language`, set at apply time) with an
    English default, so notification templates are localised without threading
    the language through every gate call.
    """
    row = db.get(Application, application_id)
    payload = row.payload if row is not None and isinstance(row.payload, dict) else {}
    return normalize_lang(payload.get("language"))


def _window_hours() -> float:
    try:
        return float(os.environ.get("A7_RATE_LIMIT_HOURS", "4"))
    except ValueError:
        return 4.0


def is_rate_limited(db: Session, recipient: str, *, template_id: str | None) -> bool:
    """True when a notification-class message already went to `recipient` inside
    the window. Only rate-limited templates are throttled; everything else is
    always allowed."""
    if template_id not in _RATE_LIMITED_TEMPLATES:
        return False
    hours = _window_hours()
    if hours <= 0:
        return False
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    row = db.execute(
        select(MessageLog.id)
        .where(
            MessageLog.recipient == recipient,
            MessageLog.template_id.in_(_RATE_LIMITED_TEMPLATES),
            MessageLog.status.in_(("sent", "stub")),
            MessageLog.created_at >= cutoff,
        )
        .limit(1)
    ).first()
    return row is not None


def log_message(
    db: Session,
    *,
    application_id: int | None,
    recipient: str,
    channel: str,
    template_id: str | None,
    rendered_body: str,
    status: str,
    provider_message_id: str | None = None,
    validated_by: str | None = None,
) -> None:
    """Append one `message_log` row on the caller's session.

    Written on the node's own session so the audit row commits atomically with
    the surrounding idempotency-ledger step (and never opens a competing
    transaction). Flushed so it is visible to `is_rate_limited` within the same
    unit of work; the ledger's commit persists it.
    """
    db.add(
        MessageLog(
            application_id=application_id,
            recipient=recipient,
            channel=channel,
            template_id=template_id,
            rendered_body=rendered_body or "",
            status=status,
            provider_message_id=provider_message_id,
            validated_by=validated_by,
        )
    )
    db.flush()
