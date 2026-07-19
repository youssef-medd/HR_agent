"""A3 email intake tests — IMAP parsing, application build, and the poll task."""

from __future__ import annotations

import base64
import imaplib
from email.message import EmailMessage

from app.models.application import Application
from app.models.job import Job
from orchestrator.email_intake import (
    IncomingCV,
    build_application,
    fetch_new_cv_attachments,
    imap_configured,
)


def _raw_email() -> bytes:
    m = EmailMessage()
    m["From"] = "Jane Doe <jane@example.io>"
    m["Subject"] = "My application"
    m["Message-ID"] = "<msg-1@example.io>"
    m.set_content("Hi, my CV is attached.")
    m.add_attachment(b"%PDF-1.4 fake cv bytes", maintype="application", subtype="pdf", filename="cv.pdf")
    return m.as_bytes()


class _FakeIMAP:
    def __init__(self, host, port):
        self.stored: list = []

    def login(self, user, password):
        return ("OK", [b""])

    def select(self, mailbox):
        return ("OK", [b"1"])

    def search(self, charset, criteria):
        return ("OK", [b"1"])

    def fetch(self, num, spec):
        return ("OK", [(b"1 (RFC822)", _raw_email())])

    def store(self, num, flag, value):
        self.stored.append((num, flag, value))

    def logout(self):
        return ("BYE", [b""])


def test_not_configured_returns_empty(monkeypatch):
    monkeypatch.delenv("IMAP_HOST", raising=False)
    assert imap_configured() is False
    assert fetch_new_cv_attachments() == []


def test_fetch_parses_attachment_and_marks_seen(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.io")
    monkeypatch.setenv("IMAP_USER", "bot@example.io")
    monkeypatch.setenv("IMAP_PASS", "secret")

    fake = _FakeIMAP("h", 993)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda host, port: fake)

    got = fetch_new_cv_attachments()

    assert len(got) == 1
    cv = got[0]
    assert cv.sender_email == "jane@example.io"
    assert cv.subject == "My application"
    assert cv.filename == "cv.pdf"
    assert cv.content == b"%PDF-1.4 fake cv bytes"
    assert cv.message_id == "<msg-1@example.io>"
    # message flagged read so it is not re-scanned.
    assert fake.stored and fake.stored[0][2] == "\\Seen"


def test_build_application_matches_upload_shape():
    inc = IncomingCV(
        sender_email="cand@x.io", subject="Hi", filename="cv.pdf",
        content=b"data", message_id="<m@x>",
    )
    row = build_application(inc, job_id=3, jd_text="Backend role")
    assert row.job_id == 3
    assert row.candidate_ref == "cand@x.io"
    assert row.state == "RECEIVED"
    assert base64.b64decode(row.payload["cv_b64"]) == b"data"
    assert row.payload["source"] == "email"
    assert row.payload["email_message_id"] == "<m@x>"
    assert row.payload["jd_text"] == "Backend role"


def test_poll_creates_application_and_enqueues(db_factory, monkeypatch):
    from orchestrator import tasks

    with db_factory() as db:
        db.add(Job(id=1, title="Backend", description="Backend role"))
        db.commit()

    inc = IncomingCV(
        sender_email="cand@x.io", subject="Application", filename="cv.pdf",
        content=b"%PDF fake", message_id="<uniq-1@x>",
    )
    monkeypatch.setattr(tasks, "imap_configured", lambda: True)
    monkeypatch.setattr(tasks, "fetch_new_cv_attachments", lambda: [inc])
    monkeypatch.setattr(tasks, "_db_factory", db_factory)

    enqueued: list = []
    monkeypatch.setattr(tasks.run_application_step, "delay", lambda *a, **k: enqueued.append(a))

    result = tasks.poll_email_inbox()

    assert result["polled"] == 1 and len(result["created"]) == 1
    app_id = result["created"][0]
    assert enqueued == [(app_id, {})]
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "RECEIVED"
        assert row.candidate_ref == "cand@x.io"
        assert row.payload["jd_text"] == "Backend role"
        assert row.payload["source"] == "email"

    # Second poll with the same message-id is deduped (no new application).
    result2 = tasks.poll_email_inbox()
    assert result2["created"] == []
