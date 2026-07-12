"""A1 CV parser tests — offline (the LLM gateway is monkeypatched).

Covers the deterministic text-extraction dispatch, the parse_cv gateway call,
and both parse_node branches (success stores CVData on the application; a
missing CV source routes the application to NEEDS_ATTENTION).
"""

from __future__ import annotations

import pytest

from app.models.application import Application
from orchestrator.agents import parser as parser_mod
from orchestrator.agents.parser import CVData, CVParseError, extract_text, parse_cv


def test_extract_text_plaintext_passthrough():
    assert extract_text("cv.txt", b"Jane Doe\nPython, SQL") == "Jane Doe\nPython, SQL"


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(CVParseError):
        extract_text("cv.rtf", b"whatever")


def test_extract_text_rejects_empty_document():
    with pytest.raises(CVParseError):
        extract_text("cv.txt", b"   \n  ")


def test_parse_cv_invokes_gateway_with_schema(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return CVData(full_name="Jane Doe", skills=["Python", "SQL"])

    monkeypatch.setattr(parser_mod, "llm_call", fake_llm_call)

    cv = parse_cv("Jane Doe — Python, SQL", user_id="42")

    assert isinstance(cv, CVData)
    assert cv.full_name == "Jane Doe"
    assert captured["profile"] == "extractor"
    assert captured["schema"] is CVData
    assert captured["metadata"]["agent"] == "A1"


def test_parse_cv_rejects_empty_text():
    with pytest.raises(CVParseError):
        parse_cv("   ")


def test_cvdata_flattens_language_objects():
    # The model sometimes returns {"name": ..., "proficiency": ...} per language.
    cv = CVData.model_validate(
        {
            "full_name": "X",
            "languages": [{"name": "Arabic", "proficiency": "Native"}, "English"],
            "skills": [{"skill": "Python"}, "SQL"],
        }
    )
    assert cv.languages == ["Arabic", "English"]
    assert cv.skills == ["Python", "SQL"]


def test_parse_cv_wraps_schema_drift_as_parse_error(monkeypatch):
    # Simulate the gateway raising a pydantic ValidationError on model output.
    def boom(**_):
        return CVData.model_validate({"experiences": "not-a-list"})

    monkeypatch.setattr(parser_mod, "llm_call", boom)
    with pytest.raises(CVParseError):
        parse_cv("some cv text")


def _seed_app(db_factory, payload: dict) -> int:
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="a@b.c", state="RECEIVED", payload=payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def test_parse_node_stores_cv_and_advances(db_factory, monkeypatch):
    from orchestrator import nodes

    monkeypatch.setattr(
        nodes, "parse_cv", lambda text, **_: CVData(full_name="Jane Doe", skills=["Python"])
    )
    app_id = _seed_app(db_factory, {"cv_text": "Jane Doe, Python developer"})

    with db_factory() as db:
        state = nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    assert state["stage"] == "PARSED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "PARSED"
        assert row.payload["cv"]["full_name"] == "Jane Doe"


def test_parse_node_routes_to_needs_attention_without_cv(db_factory):
    from orchestrator import nodes

    app_id = _seed_app(db_factory, {})  # no cv_text / cv_b64 / cv_path

    with db_factory() as db:
        state = nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    assert state["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "NEEDS_ATTENTION"
