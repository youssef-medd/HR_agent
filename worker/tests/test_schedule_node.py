"""A6 interview scheduling — end-to-end through the compiled graph.

Drives a candidate through pre-screening into scheduling, which pauses awaiting
the booking reply, then resumes with `Command(resume=)` — the mechanism the
booking endpoint uses. Confirms the PRESCREENED -> INTERVIEW_SCHEDULED advance,
exactly-once booking-link delivery across replays, and the no-book route to
NEEDS_ATTENTION.
"""

from __future__ import annotations

from langgraph.types import Command

from app.models.application import Application
from orchestrator.agents.parser import CVData
from orchestrator.agents.prescreen import AnswerInterpretation, ConsentInterpretation
from orchestrator.agents.scheduler import BookingConfirmation
from orchestrator.agents.scorer import ScoreResult
from orchestrator.checkpointer import memory_saver
from orchestrator.graph import build_graph
from orchestrator.side_effects import _sent_log_reset, _sent_log_snapshot

QUESTIONS = ["Years of experience?"]


def _seed(db_factory) -> int:
    # phone present -> WhatsApp channel, so the booking link is sent over WhatsApp
    payload = {"cv_text": "Cand — Python", "screening_questions": QUESTIONS, "phone": "21600000000"}
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="cand@x.io", state="RECEIVED", payload=payload)
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
    config = {"configurable": {"thread_id": str(app_id)}}
    graph.invoke({"application_id": app_id, "stage": "RECEIVED", "attempt": 1}, config=config)
    # consent + one answer -> PRESCREENED, now paused at the booking interrupt.
    graph.invoke(Command(resume={"candidate_message": "yes"}), config=config)
    graph.invoke(Command(resume={"candidate_message": "6 years"}), config=config)
    return config


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

    result = graph.invoke(Command(resume={"candidate_message": "booked Tue 3pm"}), config=config)

    assert result["stage"] == "INTERVIEW_SCHEDULED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "INTERVIEW_SCHEDULED"
        interview = row.payload["interview"]
        assert interview["booked"] is True
        assert interview["when"] == "Tue 3pm"
        assert interview["link"].endswith(f"/book/{app_id}")
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

    result = graph.invoke(Command(resume={"candidate_message": "none of these work"}), config=config)

    assert result["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "NEEDS_ATTENTION"
        assert row.payload["interview"]["booked"] is False
