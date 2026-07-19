"""A7 email transport + template tests — stub mode vs configured SMTP send."""

from __future__ import annotations

import smtplib

import pytest

from orchestrator import side_effects
from orchestrator.emails import EmailSendError, render_email, send_email
from orchestrator.side_effects import (
    _send_offer_impl,
    _send_rejection_impl,
    _sent_log_reset,
)


def test_render_email_versioned_and_fallback():
    subj_r, body_r = render_email("rejection@v1")
    assert subj_r == "Update on your application"
    assert "won't be moving forward" in body_r

    subj_o, body_o = render_email("offer")
    assert subj_o == "Your offer"

    # Unknown kind falls back to confirmation copy.
    subj_u, _ = render_email("mystery@v9")
    assert subj_u == "We received your application"


def test_render_email_fills_name():
    _, body = render_email("offer", name="Sara")
    assert "Hello Sara," in body
    _, body_anon = render_email("offer")
    assert "Hello," in body_anon


def test_send_email_stub_mode_no_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    def _boom(*_a, **_k):
        raise AssertionError("SMTP must not be dialed without credentials")

    monkeypatch.setattr(smtplib, "SMTP", _boom)
    assert send_email("c@x.io", "s", "b") is None


def test_send_email_configured_delivers(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "bot@welyne.local")
    monkeypatch.setenv("SMTP_PASS", "app-pass")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "noreply@welyne.local")

    captured: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured.update(host=host, port=port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            captured["tls"] = True

        def login(self, user, password):
            captured["login"] = (user, password)

        def send_message(self, msg):
            captured["to"] = msg["To"]
            captured["from"] = msg["From"]
            captured["subject"] = msg["Subject"]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    mid = send_email("cand@x.io", "Hi", "Body")

    assert mid is not None and mid.startswith("<")
    assert captured["host"] == "smtp.example.com" and captured["port"] == 587
    assert captured["tls"] is True
    assert captured["login"] == ("bot@welyne.local", "app-pass")
    assert captured["to"] == "cand@x.io"
    assert captured["from"] == "noreply@welyne.local"


def test_send_email_failure_raises(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")

    class BoomSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise smtplib.SMTPException("down")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(smtplib, "SMTP", BoomSMTP)
    with pytest.raises(EmailSendError):
        send_email("c@x.io", "s", "b")


def test_sender_impls_render_and_log(monkeypatch):
    # Stub mode: no SMTP -> email_id None, but the template is rendered and logged.
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    sent: list = []
    monkeypatch.setattr(side_effects, "send_email", lambda to, s, b: sent.append((to, s)) or None)

    _sent_log_reset()
    rej = _send_rejection_impl(1, "cand@x.io", "rejection@v1")
    off = _send_offer_impl(2, "cand2@x.io", "offer@v1")

    assert rej["kind"] == "rejection" and rej["email_id"] is None
    assert off["kind"] == "offer"
    assert sent[0][0] == "cand@x.io" and sent[0][1] == "Update on your application"
    assert sent[1][1] == "Your offer"
