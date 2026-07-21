"""A7 offer gate + A8 onboarding — the pipeline tail to ONBOARDING.

Drives a candidate all the way through, then resolves the post-interview offer
gate: approve → offer email + HIRED → onboarding kit → ONBOARDING; reject →
NEEDS_ATTENTION.
"""

from __future__ import annotations

from langgraph.types import Command

from app.agents.onboarder import OnboardingKit
from app.models.application import Application
from app.models.job import Job
from orchestrator.agents.parser import CVData
from orchestrator.agents.prescreen import AnswerInterpretation, ConsentInterpretation
from orchestrator.agents.scheduler import BookingConfirmation
from orchestrator.agents.scorer import ScoreResult
from orchestrator.checkpointer import memory_saver
from orchestrator.gates import resume_with_decision
from orchestrator.graph import build_graph
from orchestrator.side_effects import _sent_log_reset, _sent_log_snapshot

QUESTIONS = ["Years of experience?"]


def _seed(db_factory) -> int:
    with db_factory() as db:
        db.add(Job(id=1, title="Backend Engineer", department="Engineering", status="published"))
        row = Application(
            job_id=1,
            candidate_ref="cand@x.io",
            state="RECEIVED",
            payload={"cv_text": "Cand — Python", "cv": {"full_name": "Jane Doe"}, "screening_questions": QUESTIONS},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _stub(monkeypatch):
    from orchestrator import nodes

    monkeypatch.setattr(nodes, "parse_cv", lambda text, **_: CVData(full_name="Jane Doe", skills=["Python"]))
    monkeypatch.setattr(
        nodes, "score_candidate",
        lambda masked, jd, **_: ScoreResult(overall=80, recommendation="shortlist"),
    )
    monkeypatch.setattr(nodes, "interpret_consent", lambda msg, **_: ConsentInterpretation(consent=True))
    monkeypatch.setattr(
        nodes, "interpret_answer",
        lambda q, msg, **_: AnswerInterpretation(answer=msg, answered=True),
    )
    monkeypatch.setattr(
        nodes, "interpret_booking_reply",
        lambda msg, **_: BookingConfirmation(confirmed=True, when="Tue 3pm"),
    )
    monkeypatch.setattr(
        nodes, "generate_onboarding_kit",
        lambda **_: OnboardingKit(
            welcome_message="Welcome Jane!",
            checklist=["Create email"],
            week_one_plan=[],
            documents=["Employment contract"],
        ),
    )


def _drive_to_offer_gate(db_factory, graph, app_id):
    config = {"configurable": {"thread_id": str(app_id)}}
    graph.invoke({"application_id": app_id, "stage": "RECEIVED", "attempt": 1}, config=config)
    graph.invoke(Command(resume={"candidate_message": "yes"}), config=config)      # consent
    graph.invoke(Command(resume={"candidate_message": "6 years"}), config=config)  # answer
    graph.invoke(Command(resume={"candidate_message": "booked Tue 3pm"}), config=config)  # booking
    return config


def test_offer_approved_hires_and_onboards(db_factory, monkeypatch):
    _stub(monkeypatch)
    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _drive_to_offer_gate(db_factory, graph, app_id)

    # Paused at the offer gate, still INTERVIEW_SCHEDULED.
    with db_factory() as db:
        assert db.get(Application, app_id).state == "INTERVIEW_SCHEDULED"

    # Recruiter approves the offer (closes the gate), then the thread resumes.
    with db_factory() as db:
        resume_with_decision(db, app_id, "offer", "approve", resolved_by="test")
    result = graph.invoke(Command(resume={"decision": "approve"}), config=config)

    assert result["stage"] == "ONBOARDING"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "ONBOARDING"
        assert row.payload["onboarding"]["welcome_message"] == "Welcome Jane!"
        assert row.payload["onboarding"]["documents"] == ["Employment contract"]

    # Offer email sent exactly once.
    offers = [s for s in _sent_log_snapshot() if s["kind"] == "offer"]
    assert len(offers) == 1


def test_offer_rejected_routes_to_needs_attention(db_factory, monkeypatch):
    _stub(monkeypatch)
    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _drive_to_offer_gate(db_factory, graph, app_id)

    with db_factory() as db:
        resume_with_decision(db, app_id, "offer", "reject", resolved_by="test")
    result = graph.invoke(Command(resume={"decision": "reject"}), config=config)

    assert result["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        assert db.get(Application, app_id).state == "NEEDS_ATTENTION"
    assert [s for s in _sent_log_snapshot() if s["kind"] == "offer"] == []
