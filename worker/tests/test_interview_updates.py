"""A6 — replan / cancel / no-show delivery and the no-show sweep."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.application import Application

from orchestrator import side_effects
from orchestrator.agents.scheduler import build_ics
from orchestrator.tasks import _interview_update


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    side_effects._sent_log_reset()


def _seed(db, **interview) -> int:
    block = {
        "booked": True,
        "sequence": 1,
        "timezone": "UTC",
        "when": "Tue 21 Jul 2026, 10:00 (UTC)",
        "scheduled_at": "2026-07-21T10:00:00+00:00",
        "previous_scheduled_at": "2026-07-20T10:00:00+00:00",
        "link": "https://cal.com/book/1",
        **interview,
    }
    row = Application(
        job_id=1, candidate_ref="c@x.io", state="INTERVIEW_SCHEDULED",
        payload={"interview": block},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


# --- ICS --------------------------------------------------------------------


def test_ics_reschedule_reuses_the_uid_with_a_higher_sequence():
    start = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)

    ics = build_ics(
        start_utc=start, summary="Interview", uid="welyne-interview-7",
        sequence=2, organizer="hr@welyne.io", attendee="c@x.io",
    )

    assert "UID:welyne-interview-7" in ics
    assert "SEQUENCE:2" in ics
    assert "METHOD:REQUEST" in ics
    assert "STATUS:CONFIRMED" in ics
    assert "ORGANIZER;CN=Recruiting:mailto:hr@welyne.io" in ics
    assert "mailto:c@x.io" in ics


def test_ics_cancel_withdraws_the_event():
    ics = build_ics(
        start_utc=datetime(2026, 7, 21, 10, 0, tzinfo=UTC), summary="Interview",
        uid="welyne-interview-7", sequence=3, method="CANCEL",
    )

    assert "METHOD:CANCEL" in ics
    assert "STATUS:CANCELLED" in ics


# --- Delivery ---------------------------------------------------------------


def test_reschedule_notice_carries_the_updated_invite(db):
    app_id = _seed(db)

    sent = _interview_update(db, app_id, "reschedule")

    assert sent["kind"] == "interview_reschedule"
    assert sent["has_ics"] is True
    assert sent["channel"] == "email"
    assert [s["kind"] for s in side_effects._sent_log_snapshot()] == ["interview_reschedule"]


def test_no_show_notice_has_no_invite_but_carries_the_rebooking_link(db):
    app_id = _seed(db, no_show=True)

    sent = _interview_update(db, app_id, "no_show")

    assert sent["has_ics"] is False
    logged = side_effects._sent_log_snapshot()[0]
    assert logged["kind"] == "interview_no_show"


def test_delivery_is_exactly_once_per_sequence(db):
    app_id = _seed(db)

    _interview_update(db, app_id, "reschedule")
    db.commit()
    # A retried task / duplicated broker delivery must not send a second invite.
    _interview_update(db, app_id, "reschedule")

    assert len(side_effects._sent_log_snapshot()) == 1


def test_a_further_reschedule_sends_again(db):
    app_id = _seed(db)
    _interview_update(db, app_id, "reschedule")
    db.commit()

    row = db.get(Application, app_id)
    block = {**row.payload["interview"], "sequence": 2, "scheduled_at": "2026-07-23T10:00:00+00:00"}
    row.payload = {**row.payload, "interview": block}
    db.commit()

    _interview_update(db, app_id, "reschedule")

    assert len(side_effects._sent_log_snapshot()) == 2


def test_update_without_a_slot_is_a_noop(db):
    row = Application(
        job_id=1, candidate_ref="c@x.io", state="INTERVIEW_SCHEDULED",
        payload={"interview": {"booked": True}},
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert _interview_update(db, row.id, "reschedule") is None
    assert side_effects._sent_log_snapshot() == []


# --- Sweep ------------------------------------------------------------------


def test_due_no_shows_flags_only_elapsed_interviews(db):
    from app.interviews import due_no_shows

    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    fresh = _seed(db, scheduled_at=(now - timedelta(minutes=5)).isoformat())
    stale = _seed(db, scheduled_at=(now - timedelta(hours=3)).isoformat())

    due = [r.id for r in due_no_shows(db, now=now)]

    assert stale in due
    assert fresh not in due
