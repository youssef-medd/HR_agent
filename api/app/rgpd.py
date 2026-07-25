"""RGPD (GDPR) erasure + retention (spec §7).

Erasure anonymises rather than hard-deletes: the recruitment audit trail (state
history, scores, gate decisions) must survive for accountability, but every
piece of personal data is scrubbed. An anonymised application carries an
`erased` marker and a placeholder candidate reference.

Shared by the candidate-facing erase endpoint (`app.routers.public`) and the
worker's retention beat job, so both apply exactly the same redaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.message_log import MessageLog
from app.models.needs_attention import NeedsAttention

# Payload keys that carry personal data — dropped entirely on erasure. Anything
# else (score numbers, state flags, job text) is retained for audit.
_PII_PAYLOAD_KEYS = {
    "cv", "cv_text", "cv_b64", "cv_filename", "applicant_name", "phone",
    "email", "prescreen", "interview", "email_message_id", "timezone", "tz",
}


def _redacted_ref(application_id: int) -> str:
    return f"erased-{application_id}@redacted.invalid"


def anonymize_application(db: Session, row: Application, *, reason: str) -> None:
    """Scrub all personal data from one application and its side records.

    Idempotent: an already-erased row is left untouched. Does not commit — the
    caller controls the transaction boundary.
    """
    payload = row.payload or {}
    if payload.get("erased"):
        return

    retained = {k: v for k, v in payload.items() if k not in _PII_PAYLOAD_KEYS}
    retained["erased"] = True
    retained["erased_at"] = datetime.now(UTC).isoformat()
    retained["erased_reason"] = reason
    original_ref = row.candidate_ref
    row.payload = retained
    row.candidate_ref = _redacted_ref(row.id)

    # Scrub the message log (recipient addresses + rendered bodies) and any
    # free-text context captured on human-attention rows.
    for msg in db.scalars(
        select(MessageLog).where(MessageLog.recipient == original_ref)
    ).all():
        msg.recipient = "[erased]"
        msg.rendered_body = "[erased]"
    for na in db.scalars(
        select(NeedsAttention).where(NeedsAttention.application_id == row.id)
    ).all():
        na.context = {"erased": True}


def erase_candidate(db: Session, candidate_ref: str, *, reason: str = "candidate_request") -> int:
    """Anonymise every application belonging to a candidate reference.

    Matches the reference case-insensitively (email or phone). Returns the number
    of applications anonymised. Commits.
    """
    rows = db.scalars(
        select(Application).where(
            func.lower(Application.candidate_ref) == candidate_ref.strip().lower()
        )
    ).all()
    for row in rows:
        anonymize_application(db, row, reason=reason)
    db.commit()
    return len(rows)


def purge_expired(db: Session, *, months: int = 12, now: datetime | None = None) -> list[int]:
    """Anonymise applications older than `months` (retention limit). Commits.

    Returns the ids purged. Idempotent — already-erased rows are skipped by
    `anonymize_application`.
    """
    now = now or datetime.now(UTC)
    # Approximate months as 30-day units — retention is a coarse policy bound.
    cutoff = now.timestamp() - months * 30 * 24 * 3600
    purged: list[int] = []
    rows = db.scalars(select(Application)).all()
    for row in rows:
        created = row.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created.timestamp() >= cutoff:
            continue
        if (row.payload or {}).get("erased"):
            continue
        anonymize_application(db, row, reason="retention_expired")
        purged.append(row.id)
    if purged:
        db.commit()
    return purged
