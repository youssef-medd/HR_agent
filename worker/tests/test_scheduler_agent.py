"""A6 scheduling agent tests — offline (the chat gateway is monkeypatched)."""

from __future__ import annotations

import pytest

from orchestrator.agents import scheduler as scheduler_mod
from orchestrator.agents.scheduler import (
    BookingConfirmation,
    SchedulerError,
    booking_link,
    interpret_booking_reply,
)


def test_booking_link_uses_calcom_url(monkeypatch):
    monkeypatch.setenv("CALCOM_URL", "https://cal.example.com/")
    assert booking_link(42) == "https://cal.example.com/book/42"


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
