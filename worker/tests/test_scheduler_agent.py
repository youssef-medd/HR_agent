"""A6 scheduling agent tests — offline (the chat gateway is monkeypatched)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.agents import scheduler as scheduler_mod
from orchestrator.agents.scheduler import (
    BookingConfirmation,
    SchedulerError,
    booking_link,
    booking_prompt,
    build_ics,
    candidate_timezone,
    format_slots,
    interpret_booking_reply,
    propose_slots,
)


def test_booking_link_uses_calcom_url(monkeypatch):
    monkeypatch.setenv("CALCOM_URL", "https://cal.com/welyne/interview")
    assert booking_link(42) == "https://cal.com/welyne/interview?metadata[application_id]=42"


def test_booking_link_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("CALCOM_URL", raising=False)
    assert booking_link(7).endswith("/book/7")


def test_interpret_booking_uses_chat_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return BookingConfirmation(confirmed=True, when="Tue 3pm")

    monkeypatch.setattr(scheduler_mod, "llm_call", fake_llm_call)

    result = interpret_booking_reply("booked tuesday at 3", user_id="9")

    assert result.confirmed is True and result.when == "Tue 3pm"
    assert captured["profile"] == "chat"
    assert captured["schema"] is BookingConfirmation
    assert captured["metadata"]["agent"] == "A6"


def test_interpret_booking_wraps_validation_error(monkeypatch):
    def boom(**_):
        return BookingConfirmation.model_validate({"confirmed": "definitely-not-a-bool"})

    monkeypatch.setattr(scheduler_mod, "llm_call", boom)
    with pytest.raises(SchedulerError):
        interpret_booking_reply("???")


def test_propose_slots_are_business_days_utc():
    # Friday 2026-07-24 09:00 UTC -> next slots skip the weekend.
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    slots = propose_slots("UTC", now=now)
    assert len(slots) == 3
    assert all(s.tzinfo is not None for s in slots)
    assert all(s > now for s in slots)
    assert all(s.weekday() < 5 for s in slots)  # no Sat/Sun


def test_propose_slots_respects_timezone():
    now = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    # 10:00 local in Tunis (UTC+1) == 09:00 UTC for the first slot.
    first = propose_slots("Africa/Tunis", now=now)[0]
    assert first.hour == 9  # stored in UTC


def test_candidate_timezone_default_and_override(monkeypatch):
    monkeypatch.delenv("DEFAULT_TZ", raising=False)
    assert candidate_timezone({}) == "UTC"
    assert candidate_timezone({"timezone": "Europe/Paris"}) == "Europe/Paris"
    assert candidate_timezone({"timezone": "Not/AZone"}) == "UTC"  # invalid -> default


def test_format_slots_and_prompt_include_times():
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    slots = propose_slots("UTC", now=now)
    listing = format_slots(slots, "UTC")
    assert "1." in listing and "(UTC)" in listing
    prompt = booking_prompt("https://cal.com/book/1", slots, "UTC")
    assert "suggested times" in prompt and "https://cal.com/book/1" in prompt


def test_build_ics_is_valid_vevent():
    start = datetime(2026, 7, 28, 13, 0, tzinfo=UTC)
    ics = build_ics(start_utc=start, summary="Interview", uid="welyne-interview-5")
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in ics and "END:VEVENT" in ics
    assert "UID:welyne-interview-5" in ics
    assert "DTSTART:20260728T130000Z" in ics
    assert "DTEND:20260728T133000Z" in ics  # default 30 min
