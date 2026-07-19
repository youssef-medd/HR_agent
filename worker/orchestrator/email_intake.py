"""A3 — CV ingestion from an email inbox (IMAP).

The upload endpoint (`POST /applications`) is the direct-application channel;
this is the email channel. A periodic task (`orchestrator.tasks.poll_email_inbox`)
polls an IMAP mailbox for unread messages carrying a CV attachment, and turns
each attachment into a `RECEIVED` application — the exact same payload shape the
upload endpoint produces, so A1 parsing and the rest of the pipeline run
unchanged.

Env-gated like the other transports: without `IMAP_HOST`/`IMAP_USER`/
`IMAP_PASS`, `fetch_new_cv_attachments` is a no-op returning `[]`, so the poll
task idles and the test suite stays offline. Processed messages are flagged
`\\Seen`; a message-id is retained on the application payload for dedup.
"""

from __future__ import annotations

import base64
import email
import imaplib
import os
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.utils import parseaddr

from app.models.application import Application

_ALLOWED_EXT = (".pdf", ".docx", ".txt", ".md")


@dataclass
class IncomingCV:
    """One CV attachment lifted from an inbound email."""

    sender_email: str
    subject: str
    filename: str
    content: bytes
    message_id: str


def imap_configured() -> bool:
    return bool(
        os.environ.get("IMAP_HOST")
        and os.environ.get("IMAP_USER")
        and os.environ.get("IMAP_PASS")
    )


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def fetch_new_cv_attachments(limit: int = 25) -> list[IncomingCV]:
    """Fetch unread emails with CV attachments and mark them read.

    Returns one `IncomingCV` per allowed attachment. Best-effort: a message that
    yields no allowed attachment is still flagged read so it is not re-scanned.
    """
    if not imap_configured():
        return []

    host = os.environ["IMAP_HOST"]
    port = int(os.environ.get("IMAP_PORT", "993"))
    user = os.environ["IMAP_USER"]
    password = os.environ["IMAP_PASS"]
    mailbox = os.environ.get("IMAP_MAILBOX", "INBOX")

    out: list[IncomingCV] = []
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select(mailbox)
        _typ, data = conn.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[:limit]
        for num in ids:
            _typ, msg_data = conn.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            sender = parseaddr(msg.get("From"))[1]
            subject = _decode(msg.get("Subject"))
            message_id = (msg.get("Message-ID") or "").strip()

            for part in msg.walk():
                filename = part.get_filename()
                if not filename or not filename.lower().endswith(_ALLOWED_EXT):
                    continue
                content = part.get_payload(decode=True)
                if content:
                    out.append(
                        IncomingCV(
                            sender_email=sender,
                            subject=subject,
                            filename=_decode(filename),
                            content=content,
                            message_id=message_id,
                        )
                    )
            conn.store(num, "+FLAGS", "\\Seen")
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return out


def build_application(incoming: IncomingCV, job_id: int, jd_text: str | None = None) -> Application:
    """Turn an inbound CV into a `RECEIVED` application row (unsaved).

    Payload matches the upload endpoint (`cv_filename` + base64 `cv_b64`) so A1's
    `_resolve_cv_text` handles it identically, plus email provenance fields.
    """
    payload: dict[str, object] = {
        "cv_filename": incoming.filename,
        "cv_b64": base64.b64encode(incoming.content).decode("ascii"),
        "source": "email",
        "email_message_id": incoming.message_id,
        "email_subject": incoming.subject,
    }
    if jd_text:
        payload["jd_text"] = jd_text
    return Application(
        job_id=job_id,
        candidate_ref=incoming.sender_email or incoming.filename,
        state="RECEIVED",
        payload=payload,
    )
