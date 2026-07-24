"""A5 pre-screening — end-to-end through the compiled graph.

Drives a shortlisted candidate into `prescreen`, which pauses on each turn
awaiting a candidate reply, and resumes it turn by turn with `Command(resume=)`
— the same mechanism the reply endpoint uses. Because every resume replays the
whole node body, the whatsapp-send count doubles as the exactly-once assertion:
consent is re-attempted on all three replays, each question on the replays after
it, yet the ledger keeps `_SENT` at one entry per step.
"""

from __future__ import annotations

from langgraph.types import Command

from app.models.application import Application
from orchestrator.agents.parser import CVData
from orchestrator.agents.prescreen import AnswerInterpretation, ConsentInterpretation
from orchestrator.agents.scorer import ScoreResult
from orchestrator.checkpointer import memory_saver
from orchestrator.graph import build_graph
from orchestrator.side_effects import _sent_log_reset, _sent_log_snapshot

QUESTIONS = ["Years of experience?", "Notice period?"]


def test_whatsapp_recipient_prefers_phone():
    from types import SimpleNamespace

    from orchestrator.nodes import _whatsapp_recipient

    row = SimpleNamespace(candidate_ref="cand@x.io")
    # applicant-provided phone wins over the email candidate_ref
    assert _whatsapp_recipient(row, {"phone": "21693008267"}) == "21693008267"
    # then the parsed CV phone
    assert _whatsapp_recipient(row, {"cv": {"phone": "+216111"}}) == "+216111"
    # falls back to candidate_ref when no phone anywhere
    assert _whatsapp_recipient(row, {}) == "cand@x.io"


def _seed(db_factory, **payload_over) -> int:
    payload = {"cv_text": "Cand — Python", "screening_questions": QUESTIONS}
    payload.update(payload_over)
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="cand@x.io", state="RECEIVED", payload=payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _stub_pipeline(monkeypatch, *, recommendation="shortlist"):
    from orchestrator import nodes

    monkeypatch.setattr(nodes, "parse_cv", lambda text, **_: CVData(full_name="Cand", skills=["Python"]))
    monkeypatch.setattr(
        nodes, "score_candidate",
        lambda masked, jd, **_: ScoreResult(overall=80, recommendation=recommendation),
    )


def test_prescreen_happy_path(db_factory, monkeypatch):
    from orchestrator import nodes

    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(nodes, "interpret_consent", lambda msg, **_: ConsentInterpretation(consent=True))
    monkeypatch.setattr(
        nodes, "interpret_answer",
        lambda q, msg, **_: AnswerInterpretation(answer=msg, answered=True),
    )

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = {"configurable": {"thread_id": str(app_id)}}

    # Runs the pipeline; pauses at the consent interrupt.
    graph.invoke({"application_id": app_id, "stage": "RECEIVED", "attempt": 1}, config=config)
    with db_factory() as db:
        assert db.get(Application, app_id).state == "PRESCREENING"

    # Consent, then one reply per question.
    graph.invoke(Command(resume={"candidate_message": "yes"}), config=config)
    graph.invoke(Command(resume={"candidate_message": "6 years"}), config=config)
    result = graph.invoke(Command(resume={"candidate_message": "1 month"}), config=config)

    assert result["stage"] == "PRESCREENED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "PRESCREENED"
        block = row.payload["prescreen"]
        assert block["status"] == "done"
        assert block["consent"]["given"] is True and block["consent"]["at"]
        assert [a["a"] for a in block["answers"]] == ["6 years", "1 month"]
        assert [a["q"] for a in block["answers"]] == QUESTIONS

    # Exactly-once across every replay: 1 consent + 2 questions.
    sent = [s for s in _sent_log_snapshot() if s["kind"] == "whatsapp"]
    assert len(sent) == 3
    assert sum(1 for s in sent if s["body"].startswith("Hello")) == 1  # consent prompt once


def test_prescreen_no_consent_routes_to_needs_attention(db_factory, monkeypatch):
    from orchestrator import nodes

    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(nodes, "interpret_consent", lambda msg, **_: ConsentInterpretation(consent=False))

    _sent_log_reset()
    graph = build_graph(db_factory, memory_saver())
    app_id = _seed(db_factory)
    config = {"configurable": {"thread_id": str(app_id)}}

    graph.invoke({"application_id": app_id, "stage": "RECEIVED", "attempt": 1}, config=config)
    result = graph.invoke(Command(resume={"candidate_message": "no thanks"}), config=config)

    assert result["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "NEEDS_ATTENTION"
        assert row.payload["prescreen"]["consent"]["given"] is False

    # No question was ever sent — only the consent prompt.
    sent = [s for s in _sent_log_snapshot() if s["kind"] == "whatsapp"]
    assert len(sent) == 1
