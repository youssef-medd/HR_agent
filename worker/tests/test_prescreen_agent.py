"""A5 pre-screening agent tests — offline (the chat gateway is monkeypatched).

Covers consent/answer interpretation, the schema-drift -> PrescreenError path,
and the payload-override question selection.
"""

from __future__ import annotations

import pytest

from orchestrator.agents import prescreen as prescreen_mod
from orchestrator.agents.prescreen import (
    DEFAULT_QUESTIONS,
    AnswerInterpretation,
    ConsentInterpretation,
    PrescreenError,
    interpret_answer,
    interpret_consent,
    screening_questions,
)


def test_screening_questions_defaults_when_no_override():
    assert screening_questions({}) == DEFAULT_QUESTIONS
    assert screening_questions({"screening_questions": []}) == DEFAULT_QUESTIONS


def test_screening_questions_uses_payload_override():
    qs = screening_questions({"screening_questions": ["Q1?", "Q2?"]})
    assert qs == ["Q1?", "Q2?"]


def test_interpret_consent_uses_chat_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return ConsentInterpretation(consent=True)

    monkeypatch.setattr(prescreen_mod, "llm_call", fake_llm_call)

    result = interpret_consent("yes please", user_id="9")

    assert isinstance(result, ConsentInterpretation) and result.consent is True
    assert captured["profile"] == "chat"
    assert captured["schema"] is ConsentInterpretation
    assert captured["metadata"]["agent"] == "A5"
    assert captured["metadata"]["turn"] == "consent"


def test_interpret_answer_returns_structured(monkeypatch):
    monkeypatch.setattr(
        prescreen_mod, "llm_call",
        lambda **_: AnswerInterpretation(answer="5 years", answered=True),
    )
    result = interpret_answer("How many years?", "about five years", user_id="9")
    assert result.answer == "5 years" and result.answered is True


def test_generate_questions_from_spec(monkeypatch):
    from orchestrator.agents.prescreen import DEFAULT_QUESTIONS, QuestionSet, generate_questions

    # No structured spec -> default set, no LLM call.
    monkeypatch.setattr(
        prescreen_mod, "llm_call", lambda **_: (_ for _ in ()).throw(AssertionError())
    )
    assert generate_questions(title="X", job_spec=None) == DEFAULT_QUESTIONS

    # With a spec -> LLM-generated, job-specific questions.
    monkeypatch.setattr(
        prescreen_mod, "llm_call",
        lambda **_: QuestionSet(questions=["Describe a RAG pipeline you built.", "Notice period?"]),
    )
    qs = generate_questions(title="AI Engineer", job_spec={"spec": {"must_have": ["RAG"]}})
    assert qs == ["Describe a RAG pipeline you built.", "Notice period?"]


def test_generate_questions_falls_back_on_error(monkeypatch):
    from orchestrator.agents.prescreen import DEFAULT_QUESTIONS, generate_questions

    def boom(**_):
        raise RuntimeError("llm down")

    monkeypatch.setattr(prescreen_mod, "llm_call", boom)
    assert generate_questions(title="X", job_spec={"spec": {"must_have": ["Y"]}}) == DEFAULT_QUESTIONS


def test_interpret_consent_wraps_validation_error(monkeypatch):
    def boom(**_):
        return ConsentInterpretation.model_validate({"consent": "not-a-bool-and-uncoercible"})

    monkeypatch.setattr(prescreen_mod, "llm_call", boom)
    with pytest.raises(PrescreenError):
        interpret_consent("???")


def test_generate_questions_passes_language(monkeypatch):
    from orchestrator.agents.prescreen import QuestionSet, generate_questions

    captured = {}

    def cap(**kw):
        captured["content"] = kw["messages"][1]["content"]
        return QuestionSet(questions=["Q1?"])

    monkeypatch.setattr(prescreen_mod, "llm_call", cap)
    generate_questions(title="Dev", job_spec={"spec": {"must_have": ["Python"]}}, lang="fr")
    assert "French" in captured["content"]


def test_summarize_prescreen_returns_summary(monkeypatch):
    from orchestrator.agents.prescreen import (
        PrescreenFlags,
        PrescreenSlots,
        PrescreenSummary,
        summarize_prescreen,
    )

    captured = {}

    def cap(**kw):
        captured.update(profile=kw["profile"], meta=kw["metadata"])
        return PrescreenSummary(
            recap="ok",
            slots=PrescreenSlots(salary_expectation="50k"),
            flags=PrescreenFlags(contradictions=["says 5y, CV shows 2y"]),
        )

    monkeypatch.setattr(prescreen_mod, "llm_call", cap)
    out = summarize_prescreen(
        title="Dev", cv={"summary": "eng"}, answers=[{"q": "salary?", "a": "50k"}], lang="en"
    )
    assert out.recap == "ok" and out.slots.salary_expectation == "50k"
    assert out.flags.contradictions == ["says 5y, CV shows 2y"]
    assert captured["profile"] == "chat" and captured["meta"]["agent"] == "A5"


def test_summarize_prescreen_never_blocks(monkeypatch):
    from orchestrator.agents.prescreen import summarize_prescreen

    def boom(**_):
        raise RuntimeError("llm down")

    monkeypatch.setattr(prescreen_mod, "llm_call", boom)
    out = summarize_prescreen(title="X", cv={}, answers=[])
    assert out.recap == "" and out.slots.availability == ""  # empty, no raise
