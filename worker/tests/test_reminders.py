"""A6 — 24h interview reminder beat job."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.application import Application

from orchestrator import side_effects
from orchestrator.tasks import _send_due_reminders


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    side_effects._sent_log_reset()


def _seed(db, *, scheduled_at, state="INTERVIEW_SCHEDULED", reminder_sent=False, ref="c@x.io"):
    interview = {"scheduled_at": scheduled_at, "when": "Tue 3pm"}
    if reminder_sent:
        interview["reminder_sent"] = True
    row = Application(job_id=1, candidate_ref=ref, state=state, payload={"interview": interview})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def test_reminder_sent_for_interview_within_24h(db):
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    app_id = _seed(db, scheduled_at=(now + timedelta(hours=12)).isoformat())

    reminded = _send_due_reminders(db, now=now)

    assert reminded == [app_id]
    assert db.get(Application, app_id).payload["interview"]["reminder_sent"] is True
    assert [s["kind"] for s in side_effects._sent_log_snapshot()] == ["interview_reminder"]


def test_reminder_not_sent_outside_window(db):
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    _seed(db, scheduled_at=(now + timedelta(days=3)).isoformat())  # too far
    _seed(db, scheduled_at=(now - timedelta(hours=1)).isoformat())  # in the past

    assert _send_due_reminders(db, now=now) == []


def test_reminder_is_idempotent(db):
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    _seed(db, scheduled_at=(now + timedelta(hours=6)).isoformat(), reminder_sent=True)

    assert _send_due_reminders(db, now=now) == []


def test_reminder_ignores_non_scheduled_states(db):
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    _seed(db, scheduled_at=(now + timedelta(hours=6)).isoformat(), state="PRESCREENED")

    assert _send_due_reminders(db, now=now) == []
