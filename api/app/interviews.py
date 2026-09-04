"""A6 — interview lifecycle after the slot is picked.

The A6 *booking* leg lives in the orchestrator graph (`schedule_node` pauses at
PRESCREENED until the candidate confirms). Everything that happens to an already
booked interview — replanning, cancellation, no-show — happens while the graph is
parked on the A7 offer gate, so it cannot be modelled as a graph resume. This
module owns that lifecycle instead:

* the application row's `payload["interview"]` block is the record of truth
  (scheduled_at, sequence, history, no_show);
* every change appends an `ApplicationEvent` so the recruiter timeline and the
  audit trail stay complete;
* the outbound message (a fresh ICS invite that *replaces* the previous one) is
  delegated to the worker — SMTP and the ICS builder live there.

The application state itself stays INTERVIEW_SCHEDULED across a replan: the
graph is still parked on the offer gate, and flipping the row to NEEDS_ATTENTION
would desynchronise it from the checkpointer. A no-show therefore surfaces as an
open `NeedsAttention` row rather than a state change.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.needs_attention import NeedsAttention
from app.queue import enqueue_interview_update

NO_SHOW_REASON = "interview_no_show"
CANCELLED_REASON = "interview_cancelled"


def interview_minutes() -> int:
    try:
        return int(os.environ.get("INTERVIEW_MINUTES", "30"))
    except ValueError:
        return 30


def no_show_grace_minutes() -> int:
    try:
        return int(os.environ.get("NO_SHOW_GRACE_MINUTES", "30"))
    except ValueError:
        return 30


class InterviewError(RuntimeError):
    """Raised when a lifecycle action does not apply to the current row."""


def block_of(row: Application) -> dict[str, Any]:
    """The application's interview block (never None, never shared)."""
    payload = row.payload if isinstance(row.payload, dict) else {}
    return dict(payload.get("interview") or {})


def parse_slot(value: str) -> datetime:
    """Parse an ISO-8601 slot into an aware UTC datetime.

    Accepts a trailing `Z` (Cal.com and the browser both send it) and treats a
    naive timestamp as UTC rather than guessing the server's local zone.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Empty slot")
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _zone(tz: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def format_slot(start: datetime, tz: str | None = "UTC") -> str:
    """Candidate-facing rendering of a slot in their own timezone."""
    zone = _zone(tz)
    local = start.astimezone(zone)
    return f"{local:%a %d %b %Y, %H:%M} ({zone.key})"


def _save(db: Session, row: Application, block: dict[str, Any]) -> None:
    payload = row.payload if isinstance(row.payload, dict) else {}
    row.payload = {**payload, "interview": block}


def _event(
    db: Session,
    row: Application,
    kind: str,
    payload: dict[str, Any],
) -> None:
    db.add(ApplicationEvent(
        application_id=row.id,
        kind=kind,
        from_state=row.state,
        to_state=row.state,
        step="interview",
        payload=payload,
    ))


def _close_open(db: Session, application_id: int, reason: str, resolution: dict[str, Any]) -> int:
    """Close the open attention rows of one reason. Returns how many were closed."""
    rows = db.scalars(
        select(NeedsAttention).where(
            NeedsAttention.application_id == application_id,
            NeedsAttention.reason == reason,
            NeedsAttention.status == "open",
        )
    ).all()
    for item in rows:
        item.status = "closed"
        item.resolution = resolution
        item.resolved_at = datetime.now(UTC)
    return len(rows)


def book_slot(
    db: Session,
    row: Application,
    *,
    start: datetime,
    source: str,
    actor: str | None = None,
    when_text: str | None = None,
) -> dict[str, Any]:
    """Record the concrete slot a candidate picked, before the graph resumes.

    Called by the portal and by the Cal.com webhook: both know the real start
    time, and stamping it here is what lets `schedule_node` build the invite for
    the slot the candidate actually chose instead of the first proposed one.
    """
    block = block_of(row)
    block["scheduled_at"] = start.isoformat()
    block["when"] = when_text or format_slot(start, block.get("timezone"))
    block["source"] = source
    block["sequence"] = int(block.get("sequence") or 0)
    block["reminder_sent"] = False
    block.pop("no_show", None)
    block.pop("no_show_at", None)
    block["history"] = [
        *(block.get("history") or []),
        {"kind": "picked", "at": datetime.now(UTC).isoformat(), "slot": start.isoformat(),
         "source": source, "actor": actor},
    ]
    _save(db, row, block)
    _event(db, row, "interview_slot_picked",
           {"slot": start.isoformat(), "source": source, "actor": actor})
    db.commit()
    return block


def reschedule(
    db: Session,
    row: Application,
    *,
    start: datetime,
    source: str,
    actor: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Move a booked interview to a new slot and re-issue the calendar invite.

    Bumps `sequence` so the replacement ICS supersedes the previous event in the
    candidate's calendar, clears the 24h reminder flag so the new time is
    reminded, and resolves an open no-show item (replanning *is* the resolution).
    """
    if row.state not in {"INTERVIEW_SCHEDULED", "PRESCREENED"}:
        raise InterviewError(
            f"Application {row.id} is in state {row.state}; nothing to reschedule"
        )
    block = block_of(row)
    previous = block.get("scheduled_at")
    if not previous and row.state == "PRESCREENED":
        raise InterviewError("No interview booked yet — confirm a slot first")

    now = datetime.now(UTC)
    block["sequence"] = int(block.get("sequence") or 0) + 1
    block["scheduled_at"] = start.isoformat()
    block["previous_scheduled_at"] = previous
    block["when"] = format_slot(start, block.get("timezone"))
    block["reminder_sent"] = False
    block["rescheduled_at"] = now.isoformat()
    block["reschedule_count"] = int(block.get("reschedule_count") or 0) + 1
    block.pop("no_show", None)
    block.pop("no_show_at", None)
    block.pop("cancelled_at", None)
    block["booked"] = True
    block["history"] = [
        *(block.get("history") or []),
        {"kind": "rescheduled", "at": now.isoformat(), "from": previous,
         "slot": start.isoformat(), "source": source, "actor": actor, "reason": reason},
    ]
    _save(db, row, block)
    _event(db, row, "interview_rescheduled", {
        "from": previous, "to": start.isoformat(), "reason": reason,
        "source": source, "actor": actor, "sequence": block["sequence"],
    })
    _close_open(db, row.id, NO_SHOW_REASON,
                {"decision": "rescheduled", "slot": start.isoformat(), "by": actor or source})
    db.commit()
    enqueue_interview_update(row.id, "reschedule")
    return block


def cancel(
    db: Session,
    row: Application,
    *,
    source: str,
    actor: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Cancel a booked interview: withdraw the calendar event, ask for a human."""
    block = block_of(row)
    if not block.get("scheduled_at"):
        raise InterviewError("No interview booked")

    now = datetime.now(UTC)
    block["sequence"] = int(block.get("sequence") or 0) + 1
    block["booked"] = False
    block["cancelled_at"] = now.isoformat()
    block["history"] = [
        *(block.get("history") or []),
        {"kind": "cancelled", "at": now.isoformat(), "slot": block.get("scheduled_at"),
         "source": source, "actor": actor, "reason": reason},
    ]
    _save(db, row, block)
    _event(db, row, "interview_cancelled",
           {"slot": block.get("scheduled_at"), "reason": reason, "source": source, "actor": actor})
    db.add(NeedsAttention(
        application_id=row.id,
        reason=CANCELLED_REASON,
        context={"slot": block.get("scheduled_at"), "source": source, "reason": reason or ""},
    ))
    db.commit()
    enqueue_interview_update(row.id, "cancel")
    return block


def mark_no_show(
    db: Session,
    row: Application,
    *,
    source: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Flag a missed interview and queue it for a recruiter decision.

    Idempotent: a row already flagged keeps its original `no_show_at` and does
    not open a second attention item.
    """
    block = block_of(row)
    if block.get("no_show"):
        return block

    now = datetime.now(UTC)
    block["no_show"] = True
    block["no_show_at"] = now.isoformat()
    block["history"] = [
        *(block.get("history") or []),
        {"kind": "no_show", "at": now.isoformat(), "slot": block.get("scheduled_at"),
         "source": source, "actor": actor},
    ]
    _save(db, row, block)
    _event(db, row, "interview_no_show",
           {"slot": block.get("scheduled_at"), "source": source, "actor": actor})
    already_open = db.scalar(
        select(NeedsAttention).where(
            NeedsAttention.application_id == row.id,
            NeedsAttention.reason == NO_SHOW_REASON,
            NeedsAttention.status == "open",
        )
    )
    if already_open is None:
        db.add(NeedsAttention(
            application_id=row.id,
            reason=NO_SHOW_REASON,
            context={"slot": block.get("scheduled_at"), "source": source},
        ))
    db.commit()
    enqueue_interview_update(row.id, "no_show")
    return block


def mark_attended(
    db: Session,
    row: Application,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Recruiter confirms the candidate showed up — stops the no-show sweep."""
    block = block_of(row)
    now = datetime.now(UTC)
    block["outcome"] = "attended"
    block["attended_at"] = now.isoformat()
    block.pop("no_show", None)
    block.pop("no_show_at", None)
    block["history"] = [
        *(block.get("history") or []),
        {"kind": "attended", "at": now.isoformat(), "slot": block.get("scheduled_at"),
         "source": "recruiter", "actor": actor},
    ]
    _save(db, row, block)
    _event(db, row, "interview_attended", {"slot": block.get("scheduled_at"), "actor": actor})
    _close_open(db, row.id, NO_SHOW_REASON, {"decision": "attended", "by": actor or "recruiter"})
    db.commit()
    return block


def due_no_shows(db: Session, *, now: datetime | None = None) -> list[Application]:
    """INTERVIEW_SCHEDULED rows whose slot elapsed with no recorded outcome."""
    now = now or datetime.now(UTC)
    cutoff = timedelta(minutes=interview_minutes() + no_show_grace_minutes())
    rows = db.scalars(
        select(Application).where(Application.state == "INTERVIEW_SCHEDULED")
    ).all()
    due: list[Application] = []
    for row in rows:
        block = block_of(row)
        if block.get("no_show") or block.get("outcome") or block.get("cancelled_at"):
            continue
        raw = block.get("scheduled_at")
        if not raw:
            continue
        try:
            start = parse_slot(str(raw))
        except ValueError:
            continue
        if now >= start + cutoff:
            due.append(row)
    return due
