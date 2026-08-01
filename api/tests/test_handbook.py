"""A8 — handbook RAG: chunking, grounded answers, refusal, endpoints."""

from __future__ import annotations

import pytest

from app.agents import handbook as hb
from app.agents.handbook import REFUSAL, HandbookAnswer, answer_question, chunk_text


def test_chunk_text_splits_on_paragraphs():
    text = "Para one.\n\n" + ("x" * 400) + "\n\n" + ("y" * 400)
    chunks = chunk_text(text, target=500)
    assert len(chunks) >= 2
    assert all(c.strip() for c in chunks)


def test_answer_refuses_when_nothing_retrieved(monkeypatch):
    def boom(**_):
        raise AssertionError("LLM must not be called when nothing is retrieved")

    monkeypatch.setattr(hb, "llm_call", boom)
    out = answer_question(None, "What is the leave policy?", retriever=lambda *a: [])
    assert out.grounded is False and out.answer == REFUSAL


def test_answer_refuses_below_similarity_floor(monkeypatch):
    monkeypatch.setattr(hb, "MIN_SIMILARITY", 0.5)
    monkeypatch.setattr(hb, "llm_call", lambda **_: (_ for _ in ()).throw(AssertionError()))
    hits = [{"source": "hb", "ordinal": 0, "content": "irrelevant", "similarity": 0.1}]
    out = answer_question(None, "q", retriever=lambda *a: hits)
    assert out.answer == REFUSAL and out.grounded is False


def test_answer_grounded_with_citation(monkeypatch):
    captured: dict = {}

    def fake(**kw):
        captured.update(profile=kw["profile"], meta=kw["metadata"])
        return HandbookAnswer(
            answer="Employees get 20 days of annual leave.",
            grounded=True, citations=["handbook#2"],
        )

    monkeypatch.setattr(hb, "llm_call", fake)
    monkeypatch.setattr(hb, "MIN_SIMILARITY", 0.1)
    hits = [{"source": "handbook", "ordinal": 2,
             "content": "Annual leave is 20 days.", "similarity": 0.8}]
    out = answer_question(None, "How many leave days?", retriever=lambda *a: hits)
    assert out.grounded is True and "20 days" in out.answer
    assert out.citations == ["handbook#2"]
    assert captured["profile"] == "judge" and captured["meta"]["agent"] == "A8"


# --- endpoints ---------------------------------------------------------------


@pytest.fixture
def admin_header(admin_user):
    from app.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(sub=str(admin_user.id), role='admin')}"}


def test_ask_requires_auth(client):
    assert client.post("/handbook/ask", json={"question": "x"}).status_code == 401


def test_ask_refuses_offline(client, admin_header):
    # sqlite test DB: retrieval is a no-op -> refusal (no hallucination).
    resp = client.post("/handbook/ask", json={"question": "leave policy?"}, headers=admin_header)
    assert resp.status_code == 200
    assert resp.json()["grounded"] is False
    assert resp.json()["answer"] == REFUSAL


def test_ingest_requires_admin(client):
    assert client.post("/handbook/ingest", json={"source": "h", "body": "x"}).status_code == 401
