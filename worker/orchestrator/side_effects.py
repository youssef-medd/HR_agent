"""Private side-effect implementations.

Every function here has a leading underscore. That is the contract enforced
by `tests/test_gates_static.py`: no module outside `orchestrator.gates` may
reference these names. The gate layer verifies the recruiter approval exists
before invoking the underscore function.

Real senders (SMTP, WhatsApp Cloud API, Cal.com, HR system) plug in here in
later slices. Slice 1 uses a small in-process "sent log" so tests can assert
exactly-once delivery.
"""

from __future__ import annotations

import os
import re
from typing import Any

from orchestrator.emails import render_email, send_email

# In-memory sent log — the audit surface for exactly-once delivery. Kept even
# once real transports are wired: every send appends here for observability and
# is what the test suite asserts against.
# Reset per test via the `_sent_log_reset` fixture.
_SENT: list[dict[str, Any]] = []


class WhatsAppSendError(RuntimeError):
    """Raised when the WhatsApp Cloud API rejects an outbound message."""


def _wa_configured() -> bool:
    return bool(os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_ID"))


def _wa_recipient(recipient: str) -> str:
    """Normalise a recipient to the digits Meta expects as the `to` field."""
    return re.sub(r"\D", "", recipient or "")


def _wa_deliver(recipient: str, body: str) -> str | None:
    """Send one text message via the Meta WhatsApp Cloud API.

    Returns the provider message id, or None in stub mode (no credentials — the
    message is only recorded in `_SENT`). Raises `WhatsAppSendError` on an HTTP
    failure so the caller's idempotency-ledger step stays un-succeeded and the
    step can be retried.
    """
    if not _wa_configured():
        return None

    import httpx

    version = os.environ.get("WHATSAPP_API_VERSION", "v23.0")
    phone_id = os.environ["WHATSAPP_PHONE_ID"]
    token = os.environ["WHATSAPP_TOKEN"]
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _wa_recipient(recipient),
        "type": "text",
        "text": {"body": body},
    }
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise WhatsAppSendError(f"WhatsApp send failed: {exc}") from exc

    data = resp.json()
    messages = data.get("messages") or [{}]
    return messages[0].get("id")


def _sent_log_reset() -> None:
    _SENT.clear()


def _sent_log_snapshot() -> list[dict[str, Any]]:
    return list(_SENT)


def _looks_like_email(recipient: str) -> bool:
    return "@" in (recipient or "")


def _deliver_notification(recipient: str, subject: str, body: str) -> tuple[str, str | None]:
    """Route a candidate notification by channel.

    Email when the recipient is an email address, otherwise WhatsApp (the
    candidate came in through the phone/WhatsApp channel). Returns
    (channel, provider_message_id). Raises the transport's own error on failure.
    """
    if _looks_like_email(recipient):
        return "email", send_email(recipient, subject, body)
    return "whatsapp", _wa_deliver(recipient, body)


def _send_rejection_impl(application_id: int, recipient: str, template: str) -> dict[str, Any]:
    subject, body = render_email(template or "rejection")
    channel, message_id = _deliver_notification(recipient, subject, body)
    entry = {
        "kind": "rejection",
        "application_id": application_id,
        "recipient": recipient,
        "template": template,
        "channel": channel,
        "message_id": message_id,
    }
    _SENT.append(entry)
    return entry


def _send_offer_impl(application_id: int, recipient: str, template: str) -> dict[str, Any]:
    subject, body = render_email(template or "offer")
    channel, message_id = _deliver_notification(recipient, subject, body)
    entry = {
        "kind": "offer",
        "application_id": application_id,
        "recipient": recipient,
        "template": template,
        "channel": channel,
        "message_id": message_id,
    }
    _SENT.append(entry)
    return entry


def _send_confirmation_impl(application_id: int, recipient: str) -> dict[str, Any]:
    subject, body = render_email("confirmation")
    channel, message_id = _deliver_notification(recipient, subject, body)
    entry = {
        "kind": "confirmation",
        "application_id": application_id,
        "recipient": recipient,
        "channel": channel,
        "message_id": message_id,
    }
    _SENT.append(entry)
    return entry


def _publish_job_impl(job_id: int, board: str) -> dict[str, Any]:
    entry = {"kind": "publish", "job_id": job_id, "board": board}
    _SENT.append(entry)
    return entry


def _send_whatsapp_impl(application_id: int, recipient: str, body: str) -> dict[str, Any]:
    """A5 pre-screening message over WhatsApp. Non-sensitive (no recruiter gate)
    — called from `nodes.prescreen_node` through the idempotency ledger. Delivers
    via the Meta Cloud API when configured, otherwise records to `_SENT` only."""
    wa_id = _wa_deliver(recipient, body)
    entry = {
        "kind": "whatsapp",
        "application_id": application_id,
        "recipient": recipient,
        "body": body,
        "wa_message_id": wa_id,
    }
    _SENT.append(entry)
    return entry


def _send_booking_link_impl(
    application_id: int, recipient: str, link: str, body: str
) -> dict[str, Any]:
    """A6 interview booking link, sent as a WhatsApp message. Non-sensitive —
    called from `nodes.schedule_node` through the idempotency ledger. `body` is
    the full prompt text delivered to the candidate; `link` is retained on the
    record for auditing."""
    wa_id = _wa_deliver(recipient, body)
    entry = {
        "kind": "booking_link",
        "application_id": application_id,
        "recipient": recipient,
        "link": link,
        "wa_message_id": wa_id,
    }
    _SENT.append(entry)
    return entry
