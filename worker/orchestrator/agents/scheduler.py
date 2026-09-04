"""A6 — interview scheduling agent.

Drives the `PRESCREENED → INTERVIEW_SCHEDULED` leg. A pre-screened candidate is
sent a Cal.com booking link (the transport is stubbed in
`orchestrator.side_effects` for this slice); once they confirm a booked slot the
application advances to INTERVIEW_SCHEDULED. A no-book / unconfirmed /
uninterpretable reply routes to `NEEDS_ATTENTION`.

Like A5, the outbound message is templated here and the LLM is used only to
*interpret* the candidate's free-text confirmation reply, through the gateway's
`chat` profile in JSON mode (`temperature=0`, `seed=42`).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.gateway import llm_call
from pydantic import BaseModel, Field, ValidationError

PROMPT_VERSION = "schedule@v1"

_DEFAULT_CALCOM_URL = "https://cal.com"

# Interview defaults. Slots are proposed on upcoming business days at these
# local hours; each interview is INTERVIEW_MINUTES long.
_SLOT_HOURS = (10, 14, 16)
_N_SLOTS = 3
INTERVIEW_MINUTES = 30


def candidate_timezone(payload: dict | None) -> str:
    """The candidate's IANA timezone, defaulting to DEFAULT_TZ then UTC.

    Read from the application payload (`timezone`/`tz`), so proposed slots and
    the ICS invite are shown in the candidate's local time while everything is
    stored in UTC.
    """
    payload = payload or {}
    tz = (payload.get("timezone") or payload.get("tz") or os.environ.get("DEFAULT_TZ") or "UTC")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return tz


def propose_slots(
    tz: str = "UTC", *, now: datetime | None = None, count: int = _N_SLOTS
) -> list[datetime]:
    """Return `count` UTC-aware interview slots on upcoming business days.

    Deterministic given `now`: walks forward from the next day, skipping
    weekends, offering the configured local hours in order. Times are computed
    in `tz` then converted to UTC for storage.
    """
    zone = ZoneInfo(tz) if _tz_ok(tz) else ZoneInfo("UTC")
    base = (now or datetime.now(UTC)).astimezone(zone)
    slots: list[datetime] = []
    day = base.date()
    while len(slots) < count:
        day = day + timedelta(days=1)
        if day.weekday() >= 5:  # Sat/Sun
            continue
        for hour in _SLOT_HOURS:
            local = datetime.combine(day, time(hour, 0), tzinfo=zone)
            slots.append(local.astimezone(UTC))
            if len(slots) >= count:
                break
    return slots


def _tz_ok(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def format_slots(slots: list[datetime], tz: str = "UTC") -> str:
    """Human-readable numbered slot list in the candidate's local timezone."""
    zone = ZoneInfo(tz) if _tz_ok(tz) else ZoneInfo("UTC")
    lines = []
    for i, s in enumerate(slots, 1):
        local = s.astimezone(zone)
        lines.append(f"  {i}. {local:%a %d %b, %H:%M} ({tz})")
    return "\n".join(lines)


def build_ics(
    *,
    start_utc: datetime,
    summary: str,
    description: str = "",
    uid: str,
    minutes: int = INTERVIEW_MINUTES,
    sequence: int = 0,
    method: str = "REQUEST",
    organizer: str | None = None,
    attendee: str | None = None,
) -> str:
    """Build a minimal valid iCalendar VEVENT (UTC) for an interview slot.

    A replanned interview MUST reuse the same `uid` with a higher `sequence`:
    that is what makes a calendar client move the existing event instead of
    adding a second one. `method="CANCEL"` (with the bumped sequence) removes it.
    """
    end_utc = start_utc + timedelta(minutes=minutes)
    stamp = datetime.now(UTC)
    cancelled = method.upper() == "CANCEL"

    def _z(dt: datetime) -> str:
        return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    def _esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Welyne//Interview//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method.upper()}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{_z(stamp)}",
        f"DTSTART:{_z(start_utc)}",
        f"DTEND:{_z(end_utc)}",
        f"SUMMARY:{_esc(summary)}",
        f"DESCRIPTION:{_esc(description)}",
    ]
    if organizer:
        lines.append(f"ORGANIZER;CN=Recruiting:mailto:{organizer}")
    if attendee:
        lines.append(
            "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;"
            f"RSVP=TRUE:mailto:{attendee}"
        )
    lines += [
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


class BookingConfirmation(BaseModel):
    confirmed: bool = Field(description="True only if the candidate confirms they booked a slot")
    when: str = Field(default="", description="The slot the candidate booked, as they stated it")


class SchedulerError(RuntimeError):
    """Raised when a booking reply cannot be interpreted into a schema."""


def booking_link(application_id: int) -> str:
    """External Cal.com booking link for an application, or "" when unconfigured.

    When `CALCOM_URL` is set (the recruiter's real Cal.com booking page), the
    application id is attached as booking metadata so the Cal.com
    `BOOKING_CREATED` webhook can map the confirmation back to this application.

    Without it there is no external page to send anyone to: the candidate books
    through the portal's own slot buttons. Returning "" keeps a dead link off
    the portal and out of the message — a placeholder cal.com URL 404s.
    """
    base = os.environ.get("CALCOM_URL")
    if base:
        return f"{base.rstrip('/')}?metadata[application_id]={application_id}"
    return ""


def booking_prompt(
    link: str, slots: list[datetime] | None = None, tz: str = "UTC"
) -> str:
    """The booking message. `link` is wherever the candidate picks a time —
    the Cal.com page when configured, otherwise their portal."""
    slot_block = ""
    if slots:
        slot_block = "Here are three suggested times:\n" + format_slots(slots, tz) + "\n"
    where = f"Please pick a time that works for you here: {link}\n" if link else ""
    return (
        "Thanks for completing pre-screening! The next step is a short interview.\n"
        f"{slot_block}"
        f"{where}"
        "Reply with the slot you chose, or reply NO if none of the times work."
    )


_SYSTEM = (
    "You decide whether a job candidate has confirmed booking an interview slot, "
    "from their raw reply to a booking link. Respond with a single JSON object "
    "using EXACTLY these keys: confirmed (boolean — true only if they clearly say "
    "they booked / picked a time), when (string — the slot they mention, verbatim, "
    "or empty if none). A refusal, a scheduling problem, or an ambiguous reply is "
    "confirmed=false. Nothing else."
)


def interpret_booking_reply(message: str, *, user_id: str | None = None) -> BookingConfirmation:
    """Interpret a candidate's booking reply. Raises `SchedulerError` on schema drift."""
    try:
        return llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": message},
            ],
            schema=BookingConfirmation,
            user_id=user_id,
            metadata={"agent": "A6", "prompt_version": PROMPT_VERSION, "turn": "booking"},
        )
    except ValidationError as exc:
        raise SchedulerError(f"Booking reply did not match schema: {exc}") from exc
