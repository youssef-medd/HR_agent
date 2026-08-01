"""A8 — onboarding task materialisation from the generated kit."""

from __future__ import annotations

from app.models.onboarding_task import OnboardingTask

from orchestrator.nodes import _persist_onboarding_tasks

_KIT = {
    "welcome_message": "Welcome aboard!",
    "checklist": ["Create email account", "Provision laptop hardware"],
    "week_one_plan": [{"when": "Day 1", "task": "Meet the team"}],
    "documents": ["National ID (CIN)", "Bank details (RIB)", "Signed contract"],
}


def test_persist_creates_categorised_tasks(db):
    _persist_onboarding_tasks(db, application_id=1, kit=_KIT)
    tasks = db.query(OnboardingTask).filter_by(application_id=1).all()

    by_cat: dict[str, list[str]] = {}
    for t in tasks:
        by_cat.setdefault(t.category, []).append(t.label)

    assert len(by_cat["document"]) == 3
    assert "account" in by_cat and "equipment" in by_cat  # checklist split
    assert any("Day 1" in la for la in by_cat["agenda"])
    # document tasks get a due date for the reminder job
    docs = [t for t in tasks if t.category == "document"]
    assert all(t.due_at is not None and t.status == "pending" for t in docs)


def test_persist_is_idempotent(db):
    _persist_onboarding_tasks(db, application_id=1, kit=_KIT)
    _persist_onboarding_tasks(db, application_id=1, kit=_KIT)  # second run no-ops
    assert db.query(OnboardingTask).filter_by(application_id=1).count() == 6


# --- A8 reminder + escalation beat job ---------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from app.models.application import Application  # noqa: E402
from app.models.needs_attention import NeedsAttention  # noqa: E402

from orchestrator import side_effects, tasks  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    side_effects._sent_log_reset()


def _seed_doc(db, *, due_offset_h, reminded=False, ref="c@x.io"):
    row = Application(job_id=1, candidate_ref=ref, state="ONBOARDING", payload={})
    db.add(row)
    db.commit()
    db.refresh(row)
    now = datetime.now(UTC)
    t = OnboardingTask(
        application_id=row.id, category="document", label="CIN", status="pending",
        due_at=now + timedelta(hours=due_offset_h),
        reminded_at=(now - timedelta(days=1)) if reminded else None,
    )
    db.add(t)
    db.commit()
    return row.id


def test_reminder_sent_when_overdue(db, monkeypatch):
    sent: list = []
    monkeypatch.setattr(tasks, "send_email", lambda to, s, b: sent.append(to) or None)
    app_id = _seed_doc(db, due_offset_h=-1)  # already overdue, not reminded

    out = tasks._process_onboarding_docs(db, now=datetime.now(UTC))
    assert out["reminded"] == [app_id] and out["escalated"] == []
    assert sent == ["c@x.io"]
    task = db.query(OnboardingTask).filter_by(application_id=app_id).one()
    assert task.reminded_at is not None and task.status == "pending"


def test_not_reminded_before_due(db, monkeypatch):
    monkeypatch.setattr(tasks, "send_email", lambda *a: None)
    _seed_doc(db, due_offset_h=48)  # not due yet
    assert tasks._process_onboarding_docs(db, now=datetime.now(UTC)) == {
        "reminded": [], "escalated": []
    }


def test_escalates_after_grace(db, monkeypatch):
    monkeypatch.setenv("ONBOARDING_ESCALATE_DAYS", "3")
    monkeypatch.setattr(tasks, "send_email", lambda *a: None)
    # due 10 days ago, already reminded -> past the grace window
    app_id = _seed_doc(db, due_offset_h=-240, reminded=True)

    out = tasks._process_onboarding_docs(db, now=datetime.now(UTC))
    assert out["escalated"] == [app_id]
    task = db.query(OnboardingTask).filter_by(application_id=app_id).one()
    assert task.status == "expired"
    na = db.query(NeedsAttention).filter_by(application_id=app_id).all()
    assert any(n.reason == "onboarding_docs_overdue" for n in na)
