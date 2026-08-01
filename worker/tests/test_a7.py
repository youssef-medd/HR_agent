"""A7 — personalization guardrails + the no-unlogged-send-path invariant."""

from __future__ import annotations

import pytest
from app.models.message_log import MessageLog
from sqlalchemy import func, select

from orchestrator import side_effects
from orchestrator.emails import _cap_sentences, personalize_opener, render_email


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    side_effects._sent_log_reset()


def test_cap_sentences_limits_to_two():
    assert _cap_sentences("One. Two. Three. Four.") == "One. Two."
    assert _cap_sentences("Just one sentence") == "Just one sentence"


def test_personalize_opener_capped(monkeypatch):
    import orchestrator.emails as emails

    monkeypatch.setattr(emails, "llm_call", lambda **_: "First line. Second line. Third overflow.")
    out = personalize_opener("offer", "Backend Engineer", "en")
    assert out == "First line. Second line."


def test_personalize_opener_never_blocks(monkeypatch):
    import orchestrator.emails as emails

    def boom(**_):
        raise RuntimeError("llm down")

    monkeypatch.setattr(emails, "llm_call", boom)
    assert personalize_opener("rejection", "Role", "fr") == ""


def test_render_email_injects_personal():
    _, body = render_email("offer", name="Sara", personal="We loved meeting you.")
    assert "We loved meeting you." in body
    # inserted after the greeting, before the template body
    assert body.index("We loved meeting you.") < body.index("offer")


# Every candidate-facing sender must write a message_log row (spec §A7 AC:
# "aucun chemin d'envoi non journalisé n'existe").
def _senders(db):
    return [
        lambda: side_effects._send_rejection_impl(db, 1, "c@x.io", "rejection"),
        lambda: side_effects._send_offer_impl(db, 1, "c@x.io", "offer"),
        lambda: side_effects._send_confirmation_impl(db, 1, "c@x.io"),
        lambda: side_effects._send_whatsapp_impl(db, 1, "21600000000", "hi"),
        lambda: side_effects._send_booking_link_impl(db, 1, "21600000000", "link", "body"),
        lambda: side_effects._send_interview_confirmation_impl(db, 1, "c@x.io", "Tue 3pm", None),
        lambda: side_effects._send_interview_reminder_impl(db, 1, "c@x.io", "Tue 3pm"),
        lambda: side_effects._send_prescreen_invite_impl(db, 1, "c@x.io", "http://portal"),
    ]


def test_no_unlogged_send_path(db, monkeypatch):
    monkeypatch.setattr(side_effects, "personalize_opener", lambda *a, **k: "")
    before = db.execute(select(func.count()).select_from(MessageLog)).scalar_one()
    senders = _senders(db)
    for fn in senders:
        fn()
    after = db.execute(select(func.count()).select_from(MessageLog)).scalar_one()
    assert after - before == len(senders)  # one audit row per send, no exceptions
