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


def test_interpret_consent_wraps_validation_error(monkeypatch):
    def boom(**_):
        return ConsentInterpretation.model_validate({"consent": "not-a-bool-and-uncoercible"})

    monkeypatch.setattr(prescreen_mod, "llm_call", boom)
    with pytest.raises(PrescreenError):
        interpret_consent("???")
