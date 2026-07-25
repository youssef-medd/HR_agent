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

from sqlalchemy.orm import Session

from orchestrator.emails import render_email, send_email
from orchestrator.message_log import candidate_language, is_rate_limited, log_message

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


def _send_notification(
    db: Session, application_id: int, recipient: str, kind: str, subject: str, body: str
) -> dict[str, Any]:
    """Deliver a notification-class message with A7 rate-limit + audit logging.

    Rejection/offer/prescreen_invite are throttled to one per recipient per
    window (see `message_log.is_rate_limited`); a suppressed send is recorded as
    `skipped_rate_limited` and never delivered. Every send appends to `_SENT`
    (exactly-once audit) and writes a `message_log` row on the caller's session.
    """
    if is_rate_limited(db, recipient, template_id=kind):
        log_message(
            db, application_id=application_id, recipient=recipient,
            channel="email" if _looks_like_email(recipient) else "whatsapp",
            template_id=kind, rendered_body=body, status="skipped_rate_limited",
        )
        entry = {
            "kind": kind, "application_id": application_id, "recipient": recipient,
            "channel": "email" if _looks_like_email(recipient) else "whatsapp",
            "message_id": None, "status": "skipped_rate_limited",
        }
        _SENT.append(entry)
        return entry

    channel, message_id = _deliver_notification(recipient, subject, body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel=channel,
        template_id=kind, rendered_body=body,
        status="sent" if message_id else "stub", provider_message_id=message_id,
    )
    entry = {
        "kind": kind, "application_id": application_id, "recipient": recipient,
        "channel": channel, "message_id": message_id, "status": "sent",
    }
    _SENT.append(entry)
    return entry


def _send_rejection_impl(
    db: Session, application_id: int, recipient: str, template: str, lang: str | None = None
) -> dict[str, Any]:
    subject, body = render_email(
        template or "rejection", lang=lang or candidate_language(db, application_id)
    )
    return _send_notification(db, application_id, recipient, "rejection", subject, body)


def _send_offer_impl(
    db: Session, application_id: int, recipient: str, template: str, lang: str | None = None
) -> dict[str, Any]:
    subject, body = render_email(
        template or "offer", lang=lang or candidate_language(db, application_id)
    )
    return _send_notification(db, application_id, recipient, "offer", subject, body)


def _send_confirmation_impl(
    db: Session, application_id: int, recipient: str, lang: str | None = None
) -> dict[str, Any]:
    # Confirmations are exempt from the rate-limiter (not in the throttled set).
    subject, body = render_email("confirmation", lang=lang or candidate_language(db, application_id))
    return _send_notification(db, application_id, recipient, "confirmation", subject, body)


def _publish_job_impl(job_id: int, board: str) -> dict[str, Any]:
    entry = {"kind": "publish", "job_id": job_id, "board": board}
    _SENT.append(entry)
    return entry


def _send_prescreen_invite_impl(
    db: Session, application_id: int, recipient: str, link: str
) -> dict[str, Any]:
    """A7 — email a shortlisted web candidate a direct pre-screening chat link.

    Non-sensitive. Only meaningful for email recipients (web channel); the link
    opens the candidate portal prefilled so nothing must be memorised."""
    body = (
        "Hello,\n\nGood news — you've been shortlisted! The next step is a short "
        "pre-screening chat with our AI assistant (a human makes the final "
        f"decision).\n\nStart it here:\n{link}\n\nBest,\nRecruiting Team"
    )
    if is_rate_limited(db, recipient, template_id="prescreen_invite"):
        log_message(
            db, application_id=application_id, recipient=recipient, channel="email",
            template_id="prescreen_invite", rendered_body=body,
            status="skipped_rate_limited",
        )
        entry = {
            "kind": "prescreen_invite", "application_id": application_id,
            "recipient": recipient, "link": link, "email_id": None,
            "status": "skipped_rate_limited",
        }
        _SENT.append(entry)
        return entry

    email_id = send_email(recipient, "You're shortlisted — quick pre-screening", body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel="email",
        template_id="prescreen_invite", rendered_body=body,
        status="sent" if email_id else "stub", provider_message_id=email_id,
    )
    entry = {
        "kind": "prescreen_invite",
        "application_id": application_id,
        "recipient": recipient,
        "link": link,
        "email_id": email_id,
    }
    _SENT.append(entry)
    return entry


def _send_whatsapp_impl(
    db: Session, application_id: int, recipient: str, body: str
) -> dict[str, Any]:
    """A5 pre-screening message over WhatsApp. Non-sensitive (no recruiter gate)
    — called from `nodes.prescreen_node` through the idempotency ledger. Delivers
    via the Meta Cloud API when configured, otherwise records to `_SENT` only."""
    wa_id = _wa_deliver(recipient, body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel="whatsapp",
        template_id="prescreen_question", rendered_body=body,
        status="sent" if wa_id else "stub", provider_message_id=wa_id,
    )
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
    db: Session, application_id: int, recipient: str, link: str, body: str
) -> dict[str, Any]:
    """A6 interview booking link, sent as a WhatsApp message. Non-sensitive —
    called from `nodes.schedule_node` through the idempotency ledger. `body` is
    the full prompt text delivered to the candidate; `link` is retained on the
    record for auditing."""
    wa_id = _wa_deliver(recipient, body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel="whatsapp",
        template_id="booking_link", rendered_body=body,
        status="sent" if wa_id else "stub", provider_message_id=wa_id,
    )
    entry = {
        "kind": "booking_link",
        "application_id": application_id,
        "recipient": recipient,
        "link": link,
        "wa_message_id": wa_id,
    }
    _SENT.append(entry)
    return entry


def _send_interview_confirmation_impl(
    db: Session, application_id: int, recipient: str, when: str, ics: str | None = None
) -> dict[str, Any]:
    """A6 — confirm the booked interview. Email carries an ICS invite; a phone
    candidate gets a plain WhatsApp confirmation. Non-sensitive, ledger-guarded."""
    body = (
        f"Your interview is confirmed for {when}. A calendar invite is attached. "
        "We look forward to speaking with you."
    )
    if _looks_like_email(recipient):
        channel = "email"
        message_id = send_email(recipient, "Your interview is confirmed", body, ics=ics)
    else:
        channel = "whatsapp"
        message_id = _wa_deliver(recipient, body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel=channel,
        template_id="interview_confirmation", rendered_body=body,
        status="sent" if message_id else "stub", provider_message_id=message_id,
    )
    entry = {
        "kind": "interview_confirmation", "application_id": application_id,
        "recipient": recipient, "when": when, "channel": channel,
        "message_id": message_id, "has_ics": ics is not None,
    }
    _SENT.append(entry)
    return entry


def _send_interview_reminder_impl(
    db: Session, application_id: int, recipient: str, when: str
) -> dict[str, Any]:
    """A6 — 24h interview reminder. Non-sensitive; sent by the reminder beat job."""
    body = f"Reminder: your interview is scheduled for {when}. See you soon!"
    channel, message_id = _deliver_notification(recipient, "Interview reminder", body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel=channel,
        template_id="interview_reminder", rendered_body=body,
        status="sent" if message_id else "stub", provider_message_id=message_id,
    )
    entry = {
        "kind": "interview_reminder", "application_id": application_id,
        "recipient": recipient, "when": when, "channel": channel,
        "message_id": message_id,
    }
    _SENT.append(entry)
    return entry
