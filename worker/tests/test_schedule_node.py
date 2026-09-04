"""A6 interview scheduling — end-to-end through the compiled graph.

Drives a candidate through pre-screening into scheduling, which pauses twice:
first on the `interview_invite` recruiter gate, then awaiting the candidate's
booking reply. Both resume with `Command(resume=)` — the mechanism the attention
and booking endpoints use. Confirms the PRESCREENED -> INTERVIEW_SCHEDULED
advance, exactly-once booking-link delivery across replays, the declined-invite
route (rejection email, then DECLINED), and the NEEDS_ATTENTION route when the
candidate books nothing.
"""

from __future__ import annotations

from app.models.application import Application
from app.models.audit_log import AuditLog
from langgraph.types import Command

from orchestrator.agents.parser import CVData
from orchestrator.agents.prescreen import AnswerInterpretation, ConsentInterpretation
from orchestrator.agents.scheduler import BookingConfirmation
from orchestrator.agents.scorer import ScoreResult
from orchestrator.checkpointer import memory_saver
from orchestrator.gates import resume_with_decision
from orchestrator.graph import build_graph
from orchestrator.side_effects import _sent_log_reset, _sent_log_snapshot

QUESTIONS = ["Years of experience?"]


def _seed(db_factory, candidate_ref: str = "cand@x.io") -> int:
    # phone present -> WhatsApp channel, so the booking link is sent over WhatsApp
    payload = {"cv_text": "Cand — Python", "screening_questions": QUESTIONS, "phone": "21600000000"}
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref=candidate_ref, state="RECEIVED", payload=payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _stub_to_prescreened(monkeypatch):
    """Stub A1/A4/A5 so the pipeline reaches PRESCREENED offline."""
    from orchestrator import nodes

    monkeypatch.setattr(nodes, "parse_cv", lambda text, **_: CVData(full_name="Cand", skills=["Python"]))
    monkeypatch.setattr(
        nodes, "score_candidate",
        lambda masked, jd, **_: ScoreResult(overall=80, recommendation="shortlist"),
    )
    monkeypatch.setattr(nodes, "interpret_consent", lambda msg, **_: ConsentInterpretation(consent=True))
    monkeypatch.setattr(
        nodes, "interpret_answer",
        lambda q, msg, **_: AnswerInterpretation(answer=msg, answered=True),
    )


def _run_to_prescreened(db_factory, monkeypatch, graph, app_id):
    """Reach PRESCREENED, paused on the `interview_invite` gate."""
    config = {"configurable": {"thread_id": str(app_id)}}
    graph.invoke({"application_id": app_id, "stage": "RECEIVED", "attempt": 1}, config=config)
    # consent + one answer -> PRESCREENED, now paused at the recruiter gate.
    graph.invoke(Command(resume={"candidate_message": "yes"}), config=config)
    graph.invoke(Command(resume={"candidate_message": "6 years"}), config=config)
    return config


def _approve_invite(graph, config):
    """The recruiter approves inviting the candidate; slots then go out."""
    return graph.invoke(Command(resume={"decision": "approve"}), config=config)


def test_schedule_happy_path(db_factory, monkeypatch):
    from orchestrator import nodes

    _stub_to_prescreened(monkeypatch)
    monkeypatch.setattr(
        nodes, "interpret_booking_reply",
        lambda msg, **_: BookingConfirmation(confirmed=True, when="Tue 3pm"),
    )

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _run_to_prescreened(db_factory, monkeypatch, graph, app_id)

    with db_factory() as db:
        assert db.get(Application, app_id).state == "PRESCREENED"

    # No slots reach the candidate before a recruiter approves the invitation.
    assert [s for s in _sent_log_snapshot() if s["kind"] == "booking_link"] == []

    _approve_invite(graph, config)
    result = graph.invoke(Command(resume={"candidate_message": "booked Tue 3pm"}), config=config)

    assert result["stage"] == "INTERVIEW_SCHEDULED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "INTERVIEW_SCHEDULED"
        interview = row.payload["interview"]
        assert interview["booked"] is True
        assert interview["when"] == "Tue 3pm"
        # No CALCOM_URL in the test env, so there is no external booking page —
        # the portal's slot buttons are the booking surface.
        assert interview["link"] == ""
        assert interview["proposed_slots"]
        assert interview["at"]

    # Booking link sent exactly once despite replays.
    links = [s for s in _sent_log_snapshot() if s["kind"] == "booking_link"]
    assert len(links) == 1


def test_schedule_no_booking_routes_to_needs_attention(db_factory, monkeypatch):
    from orchestrator import nodes

    _stub_to_prescreened(monkeypatch)
    monkeypatch.setattr(
        nodes, "interpret_booking_reply",
        lambda msg, **_: BookingConfirmation(confirmed=False, when=""),
    )

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _run_to_prescreened(db_factory, monkeypatch, graph, app_id)
    _approve_invite(graph, config)

    result = graph.invoke(Command(resume={"candidate_message": "none of these work"}), config=config)

    assert result["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "NEEDS_ATTENTION"
        assert row.payload["interview"]["booked"] is False


def _offline_email(monkeypatch):
    """Drop SMTP credentials so a rejection send stays in stub mode (no dial-out)."""
    for var in ("SMTP_USER", "SMTP_PASS"):
        monkeypatch.delenv(var, raising=False)


def _decline_invite(db_factory, graph, config, app_id):
    """The recruiter declines the invite, closing the gate row like the API does."""
    with db_factory() as db:
        resume_with_decision(db, app_id, "interview_invite", "reject", resolved_by="test")
    return graph.invoke(Command(resume={"decision": "reject"}), config=config)


def test_recruiter_declining_the_invite_stops_the_candidate_being_asked(db_factory, monkeypatch):
    """A rejected gate must not send slots, and must not schedule anything."""
    _offline_email(monkeypatch)
    _stub_to_prescreened(monkeypatch)

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _run_to_prescreened(db_factory, monkeypatch, graph, app_id)

    result = _decline_invite(db_factory, graph, config, app_id)

    assert result["stage"] == "DECLINED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "DECLINED"
        assert row.payload["interview"]["invite_declined"] is True
        assert "proposed_slots" not in row.payload["interview"]
    assert [s for s in _sent_log_snapshot() if s["kind"] == "booking_link"] == []


def test_declined_invite_emails_the_candidate_once(db_factory, monkeypatch):
    """The candidate is told directly, not left on a silent queue item."""
    _offline_email(monkeypatch)
    _stub_to_prescreened(monkeypatch)

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = _run_to_prescreened(db_factory, monkeypatch, graph, app_id)

    _decline_invite(db_factory, graph, config, app_id)
    # Replay the resume (the gate row is already closed): the ledger must keep
    # the rejection to exactly one send.
    graph.invoke(Command(resume={"decision": "reject"}), config=config)

    rejections = [s for s in _sent_log_snapshot() if s["kind"] == "rejection"]
    assert len(rejections) == 1
    assert rejections[0]["recipient"] == "cand@x.io"

    with db_factory() as db:
        audits = db.query(AuditLog).filter(
            AuditLog.subject_id == str(app_id), AuditLog.action == "rejection_sent"
        ).all()
        assert len(audits) == 1
        assert audits[0].payload["gate"] == "interview_invite"


def test_declined_invite_without_an_email_stays_for_a_human(db_factory, monkeypatch):
    """No address to write to -> no silent close; a human still has to act."""
    _offline_email(monkeypatch)
    _stub_to_prescreened(monkeypatch)

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory, candidate_ref="21600000000")
    config = _run_to_prescreened(db_factory, monkeypatch, graph, app_id)

    result = _decline_invite(db_factory, graph, config, app_id)

    assert result["stage"] == "NEEDS_ATTENTION"
    assert [s for s in _sent_log_snapshot() if s["kind"] == "rejection"] == []


def test_invite_gate_row_is_opened_for_the_recruiter(db_factory, monkeypatch):
    """The pause must surface as an actionable queue item, not a silent stall."""
    from app.models.needs_attention import NeedsAttention

    _stub_to_prescreened(monkeypatch)
    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    _run_to_prescreened(db_factory, monkeypatch, graph, app_id)

    with db_factory() as db:
        rows = db.query(NeedsAttention).filter(
            NeedsAttention.application_id == app_id,
            NeedsAttention.gate == "interview_invite",
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "open"
        # The recruiter decides on evidence: score and pre-screening outcome.
        assert rows[0].context["score"] == 80
