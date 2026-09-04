"""A5/A6 — a number WhatsApp cannot deliver to must not wedge the pipeline.

A Meta *test* app may only message pre-registered recipients; any other number
400s with #131030 forever. These assert the two guards: the channel choice skips
such a number, and a send that slips through is recorded rather than raised.
"""

from __future__ import annotations

import httpx
import pytest
from app.models.application import Application

from orchestrator import side_effects
from orchestrator.nodes import _prescreen_channel
from orchestrator.side_effects import (
    WhatsAppRecipientNotAllowed,
    _send_whatsapp_impl,
    _wa_error,
    wa_recipient_allowed,
    wa_send,
    wa_window_open,
)


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "123")
    monkeypatch.delenv("WHATSAPP_ALLOWED_RECIPIENTS", raising=False)
    side_effects._sent_log_reset()


def _not_allowed_response() -> httpx.Response:
    return httpx.Response(
        400,
        json={"error": {
            "message": "(#131030) Recipient phone number not in allowed list",
            "code": 131030,
        }},
        request=httpx.Request("POST", "https://graph.facebook.com/v23.0/123/messages"),
    )


def test_allowlist_gates_the_channel(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "+216 93 008 267, 15551790223")

    assert wa_recipient_allowed("21693008267") is True
    assert wa_recipient_allowed("+216-93-008-267") is True  # formatting is irrelevant
    assert wa_recipient_allowed("21655123456") is False


def test_channel_falls_back_to_web_for_an_unreachable_number(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "21693008267")

    assert _prescreen_channel({"phone": "21693008267"}) == "whatsapp"
    # The number a parsed CV happened to carry is not on the test list.
    assert _prescreen_channel({"cv": {"phone": "+21655123456"}}) == "web"
    assert _prescreen_channel({}) == "web"


def test_no_allowlist_means_no_restriction():
    assert wa_recipient_allowed("21655123456") is True


def test_stub_mode_keeps_the_nominal_whatsapp_channel(monkeypatch):
    """No credentials = offline run: nothing is sent, but the channel is unchanged."""
    monkeypatch.setenv("WHATSAPP_ALLOWED_RECIPIENTS", "21693008267")
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)

    assert wa_recipient_allowed("21655123456") is True
    assert _prescreen_channel({"phone": "21655123456"}) == "whatsapp"


def test_a_blank_number_is_never_whatsapp():
    assert wa_recipient_allowed("") is False
    assert _prescreen_channel({"phone": " "}) == "web"


def test_meta_error_body_is_surfaced():
    message, code = _wa_error(_not_allowed_response())

    assert code == 131030
    assert "not in allowed list" in message


def test_send_to_a_refused_number_is_logged_not_raised(db, monkeypatch):
    def _refuse(*args, **kwargs):
        return _not_allowed_response()

    monkeypatch.setattr(httpx, "post", _refuse)
    db.add(Application(id=1, job_id=1, candidate_ref="c@x.io", state="PRESCREENING", payload={}))
    db.commit()

    entry = _send_whatsapp_impl(db, 1, "21655123456", "hello")

    assert entry["wa_message_id"] is None
    from app.models.message_log import MessageLog
    logged = db.query(MessageLog).all()
    assert [m.status for m in logged] == ["skipped_unreachable"]


def test_other_errors_still_raise(db, monkeypatch):
    def _fail(*args, **kwargs):
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid OAuth access token", "code": 190}},
            request=httpx.Request("POST", "https://graph.facebook.com/v23.0/123/messages"),
        )

    monkeypatch.setattr(httpx, "post", _fail)
    db.add(Application(id=2, job_id=1, candidate_ref="c@x.io", state="PRESCREENING", payload={}))
    db.commit()

    with pytest.raises(side_effects.WhatsAppSendError) as exc:
        _send_whatsapp_impl(db, 2, "21655123456", "hello")
    assert not isinstance(exc.value, WhatsAppRecipientNotAllowed)
    assert "Invalid OAuth access token" in str(exc.value)


# --- The 24h customer-service window ---------------------------------------


def _capture(monkeypatch) -> dict:
    """Capture the outbound payload instead of calling Meta."""
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"messages": [{"id": "wamid.OUT"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, json=json)
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


def _inbound(db, recipient: str, *, hours_ago: float) -> None:
    """Record an inbound WhatsApp turn, which is what opens the window."""
    from datetime import UTC, datetime, timedelta

    from app.models.message_log import MessageLog

    db.add(MessageLog(
        application_id=None, recipient=recipient, channel="whatsapp",
        template_id="inbound", rendered_body="hi", status="received",
        created_at=datetime.now(UTC) - timedelta(hours=hours_ago),
    ))
    db.commit()


def test_silent_number_gets_the_approved_template(db, monkeypatch):
    """First contact: only a template actually arrives, so send one."""
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "welyne_recruitment_update")
    captured = _capture(monkeypatch)

    message_id, mode = wa_send(db, "21693008267", "How many years of experience?")

    assert (message_id, mode) == ("wamid.OUT", "template")
    assert captured["json"]["type"] == "template"
    assert captured["json"]["template"]["name"] == "welyne_recruitment_update"
    # The question rides in the template's variable.
    body = captured["json"]["template"]["components"][0]["parameters"][0]["text"]
    assert body == "How many years of experience?"


def test_open_window_sends_plain_text(db, monkeypatch):
    """Once the candidate has written to us, free text is allowed and reads better."""
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "welyne_recruitment_update")
    captured = _capture(monkeypatch)
    _inbound(db, "+216 93008267", hours_ago=2)

    message_id, mode = wa_send(db, "21693008267", "And your notice period?")

    assert (message_id, mode) == ("wamid.OUT", "text")
    assert captured["json"]["text"]["body"] == "And your notice period?"


def test_window_expires_after_24h(db, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "welyne_recruitment_update")
    _capture(monkeypatch)
    _inbound(db, "21693008267", hours_ago=25)

    assert wa_window_open(db, "21693008267") is False
    assert wa_send(db, "21693008267", "still there?")[1] == "template"


def test_window_is_per_number(db, monkeypatch):
    _capture(monkeypatch)
    _inbound(db, "21693008267", hours_ago=1)

    assert wa_window_open(db, "21693008267") is True
    assert wa_window_open(db, "21655123456") is False


def test_missing_template_falls_back_to_text(db, monkeypatch):
    """A template still PENDING approval must not stall the pipeline."""
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "not_yet_approved")
    captured: dict = {}

    class _Ok:
        def raise_for_status(self):
            return None

        def json(self):
            return {"messages": [{"id": "wamid.TEXT"}]}

    calls: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json.get("type", "text"))
        if json.get("type") == "template":
            raise httpx.HTTPStatusError(
                "bad", request=httpx.Request("POST", url),
                response=httpx.Response(
                    400, json={"error": {"message": "template not found", "code": 132001}},
                    request=httpx.Request("POST", url),
                ),
            )
        captured.update(json=json)
        return _Ok()

    monkeypatch.setattr(httpx, "post", fake_post)

    message_id, mode = wa_send(db, "21693008267", "hello")

    assert (message_id, mode) == ("wamid.TEXT", "text")
    assert calls == ["template", "text"]
