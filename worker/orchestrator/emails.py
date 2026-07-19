"""A7 — transactional email transport + templates.

The recruitment pipeline sends three candidate-facing emails: an application
confirmation (non-sensitive, A5-adjacent), and — behind the A0 human gates — a
rejection and an offer. This module renders each from a versioned template and
delivers it over SMTP.

Env-gated, exactly like the WhatsApp transport: with `SMTP_USER` + `SMTP_PASS`
set it sends over SMTP (STARTTLS); without them it is a no-op that returns
`None`, so the test suite and local runs stay fully offline. An SMTP failure
raises `EmailSendError` so the caller's idempotency-ledger step stays
un-succeeded and can be retried.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

# Versioned templates keyed by "<kind>@<version>", with a bare-kind fallback.
# Deterministic copy (no LLM) — rejection/offer wording must be consistent and
# reviewable. `{name}` is filled from context when available.
_TEMPLATES: dict[str, tuple[str, str]] = {
    "confirmation": (
        "We received your application",
        "Hello{name},\n\nThanks for applying — we've received your application "
        "and our team is reviewing it. We'll be in touch soon.\n\nBest,\n"
        "Recruiting Team",
    ),
    "rejection": (
        "Update on your application",
        "Hello{name},\n\nThank you for your interest and for the time you "
        "invested in your application. After careful review, we won't be moving "
        "forward at this time. We genuinely appreciate your effort and encourage "
        "you to apply for future roles that match your profile.\n\nBest regards,\n"
        "Recruiting Team",
    ),
    "offer": (
        "Your offer",
        "Hello{name},\n\nWe're delighted to offer you the role. Our team will "
        "follow up shortly with the formal details and next steps. "
        "Congratulations!\n\nBest regards,\nRecruiting Team",
    ),
}


class EmailSendError(RuntimeError):
    """Raised when the SMTP server rejects a message."""


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def render_email(kind: str, *, name: str | None = None) -> tuple[str, str]:
    """Render (subject, body) for a template kind or "kind@version" id."""
    base = kind.split("@", 1)[0]
    subject, body = _TEMPLATES.get(kind) or _TEMPLATES.get(base) or _TEMPLATES["confirmation"]
    greeting = f" {name}" if name else ""
    return subject, body.format(name=greeting)


def send_email(to: str, subject: str, body: str) -> str | None:
    """Send one email over SMTP. Returns a Message-ID, or None in stub mode.

    Raises `EmailSendError` on any SMTP/connection failure.
    """
    if not _smtp_configured():
        return None

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM") or user

    msg = EmailMessage()
    message_id = make_msgid()
    msg["Message-ID"] = message_id
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"SMTP send failed: {exc}") from exc

    return message_id
