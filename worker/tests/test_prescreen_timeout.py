"""A5 — 48h timeout: reminder then PRESCREEN_INCOMPLETE."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.application import Application
from app.models.needs_attention import NeedsAttention

from orchestrator import side_effects
from orchestrator.tasks import _process_stale_prescreens


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    side_effects._sent_log_reset()


def _seed(db, *, updated_h_ago, ref="c@x.io", phone=None, block=None):
    payload = {"prescreen": block or {}}
    if phone:
        payload["phone"] = phone
    row = Application(job_id=1, candidate_ref=ref, state="PRESCREENING", payload=payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    # Backdate updated_at to simulate idleness (sqlite lets us set it directly).
    row.updated_at = datetime.now(UTC) - timedelta(hours=updated_h_ago)
    db.commit()
    return row.id


def test_reminder_sent_after_48h(db):
    app_id = _seed(db, updated_h_ago=50, ref="web@x.io")
    out = _process_stale_prescreens(db, now=datetime.now(UTC))
    assert out["reminded"] == [app_id] and out["incomplete"] == []
    row = db.get(Application, app_id)
    assert row.state == "PRESCREENING"  # still open after just the reminder
    assert row.payload["prescreen"]["reminder_at"]
    # web candidate -> invite email re-sent
    assert any(s["kind"] == "prescreen_invite" for s in side_effects._sent_log_snapshot())


def test_not_touched_before_48h(db):
    app_id = _seed(db, updated_h_ago=10)
    assert _process_stale_prescreens(db, now=datetime.now(UTC)) == {"reminded": [], "incomplete": []}
    assert db.get(Application, app_id).state == "PRESCREENING"


def test_marked_incomplete_after_second_window(db):
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    # reminder already sent 50h ago, idle well past the first window
    block = {"reminder_at": (now - timedelta(hours=50)).isoformat()}
    app_id = _seed(db, updated_h_ago=100, block=block)
    out = _process_stale_prescreens(db, now=now)
    assert out["incomplete"] == [app_id]
    row = db.get(Application, app_id)
    assert row.state == "NEEDS_ATTENTION"
    assert row.payload["prescreen"]["status"] == "incomplete"
    na = db.query(NeedsAttention).filter_by(application_id=app_id).all()
    assert any(n.reason == "prescreen_incomplete" for n in na)
