"""A7 — message_log audit rows, per-candidate rate limiting, bilingual copy."""

from __future__ import annotations

import pytest
from app.models.application import Application
from app.models.message_log import MessageLog
from sqlalchemy import func, select

from orchestrator import side_effects
from orchestrator.emails import normalize_lang, render_email
from orchestrator.message_log import candidate_language, is_rate_limited


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(side_effects, "send_email", lambda *a, **k: None)
    side_effects._sent_log_reset()


def _count(db, **filters) -> int:
    stmt = select(func.count()).select_from(MessageLog)
    for k, v in filters.items():
        stmt = stmt.where(getattr(MessageLog, k) == v)
    return db.execute(stmt).scalar_one()


def test_send_writes_message_log_row(db):
    side_effects._send_rejection_impl(db, 1, "cand@x.io", "rejection@v1")
    assert _count(db, recipient="cand@x.io", template_id="rejection", status="stub") == 1


def test_rate_limit_suppresses_second_notification(db):
    first = side_effects._send_rejection_impl(db, 1, "cand@x.io", "rejection")
    second = side_effects._send_rejection_impl(db, 1, "cand@x.io", "rejection")
    assert first["status"] == "sent"  # stub delivery still counts as a send
    assert second["status"] == "skipped_rate_limited"
    # one delivered (stub) + one suppressed row
    assert _count(db, recipient="cand@x.io", status="stub") == 1
    assert _count(db, recipient="cand@x.io", status="skipped_rate_limited") == 1


def test_confirmation_is_exempt_from_rate_limit(db):
    side_effects._send_confirmation_impl(db, 1, "cand@x.io")
    side_effects._send_confirmation_impl(db, 1, "cand@x.io")
    # both delivered — confirmations are never throttled
    assert _count(db, recipient="cand@x.io", template_id="confirmation", status="stub") == 2


def test_interactive_whatsapp_not_throttled(db):
    side_effects._send_whatsapp_impl(db, 1, "21693008267", "Q1?")
    side_effects._send_whatsapp_impl(db, 1, "21693008267", "Q2?")
    assert not is_rate_limited(db, "21693008267", template_id="prescreen_question")
    assert _count(db, recipient="21693008267", template_id="prescreen_question") == 2


def test_rate_limit_disabled_when_window_zero(db, monkeypatch):
    monkeypatch.setenv("A7_RATE_LIMIT_HOURS", "0")
    side_effects._send_rejection_impl(db, 1, "cand@x.io", "rejection")
    second = side_effects._send_rejection_impl(db, 1, "cand@x.io", "rejection")
    assert second["status"] == "sent"


def test_bilingual_templates():
    _, en = render_email("rejection", lang="en")
    _, fr = render_email("rejection", lang="fr")
    assert "Best regards" in en
    assert "Cordialement" in fr
    # unknown locale falls back to English
    assert normalize_lang("es") == "en"


def test_candidate_language_from_payload(db):
    db.add(Application(id=7, job_id=1, candidate_ref="c@x.io", state="SCORED",
                       payload={"language": "FR"}))
    db.commit()
    assert candidate_language(db, 7) == "fr"
    assert candidate_language(db, 999) == "en"  # missing -> default
