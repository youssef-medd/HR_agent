"""Outbound WhatsApp transport — stub mode vs configured Meta Cloud API send."""

from __future__ import annotations

import pytest

from orchestrator.side_effects import (
    WhatsAppSendError,
    _send_whatsapp_impl,
    _sent_log_reset,
    _sent_log_snapshot,
)


def test_stub_mode_records_without_http(monkeypatch):
    # No credentials -> stub mode: message recorded, no provider id, httpx untouched.
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)

    import httpx

    def _boom(*_a, **_k):
        raise AssertionError("httpx must not be called without credentials")

    monkeypatch.setattr(httpx, "post", _boom)

    _sent_log_reset()
    entry = _send_whatsapp_impl(1, "+21620000000", "hello")
    assert entry["wa_message_id"] is None
    assert _sent_log_snapshot()[-1]["body"] == "hello"


def test_configured_mode_posts_to_meta(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")
    monkeypatch.setenv("WHATSAPP_API_VERSION", "v23.0")

    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"messages": [{"id": "wamid.OUT"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    _sent_log_reset()
    entry = _send_whatsapp_impl(7, "+1 (786) 355-9966", "hi there")

    assert entry["wa_message_id"] == "wamid.OUT"
    assert captured["url"] == "https://graph.facebook.com/v23.0/12345/messages"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"]["to"] == "17863559966"  # normalised to digits
    assert captured["json"]["text"]["body"] == "hi there"


def test_http_failure_raises(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")

    import httpx

    def fake_post(*_a, **_k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(WhatsAppSendError):
        _send_whatsapp_impl(1, "+21620000000", "hello")
