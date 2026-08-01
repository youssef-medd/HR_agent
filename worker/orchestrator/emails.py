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
import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import quote

from app.gateway import llm_call

_PERSONALIZE_SYSTEM = (
    "You write ONE short, warm, professional opening sentence (at most two "
    "sentences) for a recruitment {kind} message to a candidate for the '{title}' "
    "role, in {lang}. Rules: no new facts, no promises, no salary, no dates, no "
    "company-specific claims — only a human, considerate tone. Plain text only, "
    "no greeting, no signature."
)


def _cap_sentences(text: str, limit: int = 2) -> str:
    """Guardrail: keep at most `limit` sentences of a personalization slot."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(p for p in parts[:limit] if p).strip()


def personalize_opener(
    kind: str, title: str, lang: str | None = None, *, user_id: str | None = None
) -> str:
    """A7 personalization slot: a bounded, LLM-written opening line.

    Best-effort — returns "" on any failure so a message is never blocked, and
    the output is hard-capped to two sentences (spec §A7 'max 2 phrases')."""
    from orchestrator.emails import normalize_lang  # local: defined below

    lang_name = {"en": "English", "fr": "French", "ar": "Arabic"}.get(normalize_lang(lang), "English")
    system = _PERSONALIZE_SYSTEM.format(kind=kind, title=title or "the role", lang=lang_name)
    try:
        out = llm_call(
            profile="extractor",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Write the opening line for a {kind} message."},
            ],
            user_id=user_id,
            metadata={"agent": "A7", "prompt_version": "personalize@v1", "kind": kind},
        )
        return _cap_sentences(str(out or "").strip())
    except Exception:  # noqa: BLE001 — personalization must never block a send
        return ""


def portal_link(email: str, application_id: int) -> str:
    """Deep link into the candidate portal, prefilled — no reference to memorise."""
    base = (os.environ.get("PORTAL_URL") or "http://localhost:3001").rstrip("/")
    return f"{base}/portal?email={quote(email)}&ref={application_id}"

# Deterministic copy (no LLM) — rejection/offer wording must be consistent and
# reviewable. `{name}` is filled from context when available. Templates are
# bilingual (EN/FR); the caller passes the candidate's language.
_TEMPLATES_EN: dict[str, tuple[str, str]] = {
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

_TEMPLATES_FR: dict[str, tuple[str, str]] = {
    "confirmation": (
        "Nous avons bien reçu votre candidature",
        "Bonjour{name},\n\nMerci pour votre candidature — nous l'avons bien "
        "reçue et notre équipe l'examine. Nous reviendrons vers vous "
        "prochainement.\n\nCordialement,\nL'équipe de recrutement",
    ),
    "rejection": (
        "Suite donnée à votre candidature",
        "Bonjour{name},\n\nNous vous remercions de votre intérêt et du temps "
        "consacré à votre candidature. Après un examen attentif, nous ne "
        "donnerons pas suite pour le moment. Nous apprécions sincèrement vos "
        "efforts et vous encourageons à postuler à de futurs postes "
        "correspondant à votre profil.\n\nCordialement,\nL'équipe de recrutement",
    ),
    "offer": (
        "Votre offre",
        "Bonjour{name},\n\nNous avons le plaisir de vous proposer le poste. "
        "Notre équipe reviendra vers vous très prochainement avec les détails "
        "et les prochaines étapes. Félicitations !\n\nCordialement,\n"
        "L'équipe de recrutement",
    ),
}

_TEMPLATES_BY_LANG: dict[str, dict[str, tuple[str, str]]] = {
    "en": _TEMPLATES_EN,
    "fr": _TEMPLATES_FR,
}


def normalize_lang(lang: str | None) -> str:
    """Collapse a locale to a supported template language ('en' or 'fr')."""
    code = (lang or "").strip().lower()[:2]
    return code if code in _TEMPLATES_BY_LANG else "en"


class EmailSendError(RuntimeError):
    """Raised when the SMTP server rejects a message."""


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def render_email(
    kind: str, *, name: str | None = None, lang: str | None = None, personal: str = ""
) -> tuple[str, str]:
    """Render (subject, body) for a template kind in the candidate's language.

    `personal` is A7's bounded LLM opener; when present it is inserted as the
    first paragraph after the greeting."""
    base = kind.split("@", 1)[0]
    table = _TEMPLATES_BY_LANG[normalize_lang(lang)]
    subject, body = table.get(base) or table["confirmation"]
    greeting = f" {name}" if name else ""
    rendered = body.format(name=greeting)
    if personal:
        rendered = rendered.replace("\n\n", f"\n\n{personal}\n\n", 1)
    return subject, rendered


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    ics: str | None = None,
    ics_filename: str = "interview.ics",
) -> str | None:
    """Send one email over SMTP. Returns a Message-ID, or None in stub mode.

    When `ics` is given, a text/calendar invite is attached (A6 interview
    confirmation). Raises `EmailSendError` on any SMTP/connection failure.
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
    if ics is not None:
        msg.add_attachment(
            ics.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename=ics_filename,
        )

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"SMTP send failed: {exc}") from exc

    return message_id
