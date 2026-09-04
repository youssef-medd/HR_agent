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
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.message_log import MessageLog
from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestrator.emails import personalize_opener, render_email, send_email
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


# Meta rejects a send to a number that is not on the test app's recipient list
# with this code. It is a property of the *recipient*, not a transient failure,
# so retrying can never succeed.
_WA_RECIPIENT_NOT_ALLOWED = 131030


def wa_recipient_allowed(recipient: str) -> bool:
    """Whether this WhatsApp app is permitted to message `recipient`.

    A Meta *test* number may only message a handful of pre-registered
    recipients; every other number 400s with #131030, forever. Set
    `WHATSAPP_ALLOWED_RECIPIENTS` (comma-separated, any formatting) to that list
    and a candidate whose CV carries some other number is routed to the
    web/portal channel instead of wedging the pipeline on an impossible send.

    Unset = no restriction: a production number can message anyone, and stub
    mode (no credentials) keeps its nominal WhatsApp channel so offline runs
    still exercise the same path.
    """
    digits = _wa_recipient(recipient)
    if not digits:
        return False
    allowed = os.environ.get("WHATSAPP_ALLOWED_RECIPIENTS", "").strip()
    if not allowed or not _wa_configured():
        return True
    return digits in {_wa_recipient(entry) for entry in allowed.split(",") if entry.strip()}


class WhatsAppRecipientNotAllowed(WhatsAppSendError):
    """The number is not on the WhatsApp app's allowed recipient list (#131030)."""


def wa_window_open(db: Session, recipient: str) -> bool:
    """True if this number wrote to us inside WhatsApp's 24h service window.

    WhatsApp only allows free-form text while that window is open; outside it a
    business-initiated message must be an approved template. Meta does not
    always reject a late free-form send — it can accept it and quietly drop it —
    so the window has to be tracked on our side rather than inferred from errors.
    """
    digits = _wa_recipient(recipient)
    if not digits:
        return False
    since = datetime.now(UTC) - timedelta(hours=24)
    row = db.scalar(
        select(MessageLog)
        .where(
            MessageLog.channel == "whatsapp",
            MessageLog.template_id == "inbound",
            MessageLog.created_at >= since,
        )
        .order_by(MessageLog.id.desc())
    )
    # Recipients are stored as the candidate wrote them; compare on digits.
    if row is None:
        return False
    return _wa_recipient(row.recipient) == digits


def _wa_deliver_template(recipient: str, body: str) -> str | None:
    """Send `body` inside the approved utility template's single variable.

    The template is what makes a first contact (or any send after 24h silence)
    actually arrive. Returns None when no template is configured, so the caller
    can fall back to plain text.
    """
    name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "").strip()
    if not name or not _wa_configured():
        return None

    import httpx

    version = os.environ.get("WHATSAPP_API_VERSION", "v23.0")
    phone_id = os.environ["WHATSAPP_PHONE_ID"]
    token = os.environ["WHATSAPP_TOKEN"]
    lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en_US")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _wa_recipient(recipient),
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": body}]}
            ],
        },
    }
    try:
        resp = httpx.post(
            f"https://graph.facebook.com/{version}/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail, code = _wa_error(exc.response)
        if code == _WA_RECIPIENT_NOT_ALLOWED:
            raise WhatsAppRecipientNotAllowed(detail) from exc
        # A template still pending approval, renamed, or missing in this
        # language: fall back to plain text rather than failing the step.
        return None
    except httpx.HTTPError:
        return None

    messages = (resp.json().get("messages") or [{}])
    return messages[0].get("id")


def wa_send(db: Session, recipient: str, body: str) -> tuple[str | None, str]:
    """Deliver one WhatsApp message the way WhatsApp actually permits.

    Inside the 24h window plain text is allowed and reads naturally. Outside it,
    only an approved template will arrive, so the message rides in the
    template's variable. Returns (provider_message_id, mode).
    """
    if wa_window_open(db, recipient):
        return _wa_deliver(recipient, body), "text"

    template_id = _wa_deliver_template(recipient, body)
    if template_id is not None:
        return template_id, "template"
    # No usable template — send as text so offline/stub runs and configured
    # production numbers both behave as before.
    return _wa_deliver(recipient, body), "text"


def _wa_error(response: Any) -> tuple[str, int | None]:
    """Meta's error message + numeric code from a failed Cloud API response."""
    try:
        err = (response.json() or {}).get("error") or {}
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}", None
    message = err.get("message") or f"HTTP {response.status_code}"
    code = err.get("code")
    return message, int(code) if isinstance(code, int) else None


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
    except httpx.HTTPStatusError as exc:
        # Surface Meta's own reason — `raise_for_status` only carries the status,
        # which turns every misconfiguration into the same opaque "400".
        detail, code = _wa_error(exc.response)
        if code == _WA_RECIPIENT_NOT_ALLOWED:
            raise WhatsAppRecipientNotAllowed(detail) from exc
        raise WhatsAppSendError(f"WhatsApp send failed: {detail}") from exc
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
    if not wa_recipient_allowed(recipient):
        # Nothing to deliver to — recorded by the caller as a stub send rather
        # than raising on a number this WhatsApp app may not message.
        return "whatsapp", None
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


def _job_title(db: Session, application_id: int) -> str:
    """Best-effort job title for an application (for A7 personalization)."""
    from app.models.application import Application
    from app.models.job import Job

    app_row = db.get(Application, application_id)
    if app_row is None:
        return ""
    job = db.get(Job, app_row.job_id)
    return job.title if job is not None else ""


def _send_rejection_impl(
    db: Session, application_id: int, recipient: str, template: str, lang: str | None = None
) -> dict[str, Any]:
    lang = lang or candidate_language(db, application_id)
    personal = personalize_opener("rejection", _job_title(db, application_id), lang,
                                  user_id=str(application_id))
    subject, body = render_email(template or "rejection", lang=lang, personal=personal)
    return _send_notification(db, application_id, recipient, "rejection", subject, body)


def _send_offer_impl(
    db: Session, application_id: int, recipient: str, template: str, lang: str | None = None
) -> dict[str, Any]:
    lang = lang or candidate_language(db, application_id)
    personal = personalize_opener("offer", _job_title(db, application_id), lang,
                                  user_id=str(application_id))
    subject, body = render_email(template or "offer", lang=lang, personal=personal)
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
    via the Meta Cloud API when configured, otherwise records to `_SENT` only.

    A recipient WhatsApp refuses outright (#131030 — not on the app's allowed
    list) is recorded as `skipped_unreachable` instead of raising: retrying can
    never succeed, and a candidate must not be stranded mid-conversation because
    their CV carried a number this WhatsApp app may not message.
    """
    status = "stub"
    mode = "text"
    try:
        wa_id, mode = wa_send(db, recipient, body)
        if wa_id:
            status = "sent"
    except WhatsAppRecipientNotAllowed:
        wa_id = None
        status = "skipped_unreachable"
    log_message(
        db, application_id=application_id, recipient=recipient, channel="whatsapp",
        template_id="prescreen_question" if mode == "text" else "prescreen_question_template",
        rendered_body=body, status=status, provider_message_id=wa_id,
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
    status = "stub"
    try:
        wa_id, _mode = wa_send(db, recipient, body)
        if wa_id:
            status = "sent"
    except WhatsAppRecipientNotAllowed:
        wa_id = None
        status = "skipped_unreachable"
    log_message(
        db, application_id=application_id, recipient=recipient, channel="whatsapp",
        template_id="booking_link", rendered_body=body,
        status=status, provider_message_id=wa_id,
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
    candidate gets a plain WhatsApp confirmation. Non-sensitive, ledger-guarded.

    A number WhatsApp refuses is logged as `skipped_unreachable` rather than
    raised: the interview is already booked, and failing the send here would
    roll the whole scheduling step back over a message we can never deliver.
    """
    body = (
        f"Your interview is confirmed for {when}. A calendar invite is attached. "
        "We look forward to speaking with you."
    )
    status = "stub"
    if _looks_like_email(recipient):
        channel = "email"
        message_id = send_email(recipient, "Your interview is confirmed", body, ics=ics)
    else:
        channel = "whatsapp"
        try:
            message_id = _wa_deliver(recipient, body)
        except WhatsAppRecipientNotAllowed:
            message_id = None
            status = "skipped_unreachable"
    if message_id:
        status = "sent"
    log_message(
        db, application_id=application_id, recipient=recipient, channel=channel,
        template_id="interview_confirmation", rendered_body=body,
        status=status, provider_message_id=message_id,
    )
    entry = {
        "kind": "interview_confirmation", "application_id": application_id,
        "recipient": recipient, "when": when, "channel": channel,
        "message_id": message_id, "has_ics": ics is not None,
    }
    _SENT.append(entry)
    return entry


_INTERVIEW_UPDATE_COPY: dict[str, tuple[str, str]] = {
    "reschedule": (
        "Your interview has been rescheduled",
        "Your interview has been moved to {when}{from_clause}. The updated calendar "
        "invite is attached and replaces the previous one.",
    ),
    "cancel": (
        "Your interview has been cancelled",
        "Your interview scheduled for {when} has been cancelled. The calendar entry "
        "is withdrawn; we will contact you shortly about the next step.",
    ),
    "no_show": (
        "We missed you at your interview",
        "We were not able to meet you at {when}. If something came up, you can pick "
        "a new time here: {link}",
    ),
}


def _send_interview_update_impl(
    db: Session,
    application_id: int,
    recipient: str,
    kind: str,
    when: str,
    *,
    previous_when: str | None = None,
    link: str = "",
    ics: str | None = None,
) -> dict[str, Any]:
    """A6 — replan / cancellation / no-show notice for an already booked interview.

    Non-sensitive (no rejection, offer or publication), so it is delivered
    directly like the confirmation it supersedes. The reschedule and cancel
    variants carry an ICS with the same UID and a bumped SEQUENCE, which is what
    makes the candidate's calendar update the existing event instead of adding a
    second one.
    """
    subject, template = _INTERVIEW_UPDATE_COPY.get(kind, _INTERVIEW_UPDATE_COPY["reschedule"])
    from_clause = f" (previously {previous_when})" if previous_when else ""
    body = template.format(when=when, from_clause=from_clause, link=link or "your portal")

    if _looks_like_email(recipient):
        channel = "email"
        message_id = send_email(recipient, subject, body, ics=ics)
    else:
        channel = "whatsapp"
        message_id = _wa_deliver(recipient, body)
    log_message(
        db, application_id=application_id, recipient=recipient, channel=channel,
        template_id=f"interview_{kind}", rendered_body=body,
        status="sent" if message_id else "stub", provider_message_id=message_id,
    )
    entry = {
        "kind": f"interview_{kind}", "application_id": application_id,
        "recipient": recipient, "when": when, "previous_when": previous_when,
        "channel": channel, "message_id": message_id, "has_ics": ics is not None,
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
