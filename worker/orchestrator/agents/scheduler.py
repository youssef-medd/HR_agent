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

from pydantic import BaseModel, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "schedule@v1"

_DEFAULT_CALCOM_URL = "https://cal.com"


class BookingConfirmation(BaseModel):
    confirmed: bool = Field(description="True only if the candidate confirms they booked a slot")
    when: str = Field(default="", description="The slot the candidate booked, as they stated it")


class SchedulerError(RuntimeError):
    """Raised when a booking reply cannot be interpreted into a schema."""


def booking_link(application_id: int) -> str:
    """Deterministic Cal.com booking link for an application.

    Real link creation via the Cal.com API is a later slice; for now the link is
    derived from `CALCOM_URL` so the stub transport has something to send.
    """
    base = os.environ.get("CALCOM_URL") or _DEFAULT_CALCOM_URL
    return f"{base.rstrip('/')}/book/{application_id}"


def booking_prompt(link: str) -> str:
    return (
        "Thanks for completing pre-screening! The next step is a short interview. "
        f"Please pick a time that works for you here: {link}\n"
        "Reply here once you've booked (tell me the slot you chose), or reply NO "
        "if none of the times work."
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
