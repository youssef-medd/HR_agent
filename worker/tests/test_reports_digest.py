"""A9 — weekly admin digest + nightly snapshot aggregation."""

from __future__ import annotations

import pytest
from app.models.application import Application
from app.models.report_snapshot import ReportSnapshot
from app.models.user import User

from orchestrator import tasks


@pytest.fixture(autouse=True)
def _stub_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)


def test_digest_body_has_kpis():
    body = tasks._digest_body(
        {
            "total_applications": 12,
            "funnel": [{"stage": "RECEIVED", "reached": 12}, {"stage": "HIRED", "reached": 2}],
            "shortlist_rate": 0.5,
            "hire_rate": 0.1667,
            "avg_score": 71.2,
            "open_gates": 3,
        }
    )
    assert "Applications: 12" in body
    assert "RECEIVED 12" in body and "HIRED 2" in body
    assert "Open human-review gates: 3" in body


def test_send_admin_digest_emails_admins(db, monkeypatch):
    sent: list = []
    monkeypatch.setattr(tasks, "send_email", lambda to, s, b: sent.append((to, s)) or None)

    db.add_all([
        User(email="admin@welyne.local", password_hash="x", role="admin"),
        User(email="viewer@welyne.local", password_hash="x", role="viewer"),  # not an admin
        Application(job_id=1, candidate_ref="a@x.io", state="SCORED",
                    payload={"score": {"overall": 80}}),
    ])
    db.commit()

    recipients = tasks._send_admin_digest(db)
    assert recipients == ["admin@welyne.local"]
    assert sent and sent[0][0] == "admin@welyne.local"
    assert sent[0][1].startswith("Welyne HR")


def test_send_admin_digest_no_admins(db, monkeypatch):
    monkeypatch.setattr(tasks, "send_email", lambda *a: None)
    assert tasks._send_admin_digest(db) == []


def test_snapshot_persists_metrics(db):
    from app.routers.reports import compute_overview

    db.add(Application(job_id=1, candidate_ref="a@x.io", state="SCORED",
                       payload={"score": {"overall": 90}}))
    db.commit()

    metrics = compute_overview(db).model_dump()
    db.add(ReportSnapshot(metrics=metrics))
    db.commit()

    row = db.query(ReportSnapshot).one()
    assert row.metrics["total_applications"] == 1
    assert row.metrics["score_distribution"]["85-100"] == 1
