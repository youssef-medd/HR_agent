"""A3 — candidate deduplication.

Resolves an incoming parsed CV to a candidate identity. Strong match is an
exact salted-hash hit on email or phone (same person, re-applying). A weaker
fuzzy full-name match is reported as a *possible* duplicate for recruiter
review but never auto-merged (two different people can share a name).

Returns a verdict dict persisted on the application payload; the resolved
candidate id is written back to `applications.candidate_id`.
"""

from __future__ import annotations

import hashlib
import os
import re
from difflib import SequenceMatcher
from typing import Any

from app.models.candidate import Candidate
from sqlalchemy import select
from sqlalchemy.orm import Session

_NAME_MATCH_THRESHOLD = 0.92


def _salt() -> str:
    return os.environ.get("PII_MASK_SALT", "")


def _hash(value: str) -> str | None:
    """Salted SHA-256 of a normalized contact value; None when empty."""
    norm = re.sub(r"\s+", "", (value or "").strip().lower())
    if not norm:
        return None
    return hashlib.sha256((_salt() + norm).encode("utf-8")).hexdigest()


def _norm_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def dedup_candidate(db: Session, cv: dict[str, Any]) -> dict[str, Any]:
    """Resolve `cv` to a candidate identity and return a dedup verdict.

    Verdict keys: duplicate (bool — strong email/phone match), candidate_id,
    matched_on ('email'|'phone'|None), possible_match_id (fuzzy-name hit, not
    merged).
    """
    email_hash = _hash(cv.get("email", ""))
    phone_hash = _hash(cv.get("phone", ""))
    name = _norm_name(cv.get("full_name", ""))

    existing: Candidate | None = None
    matched_on: str | None = None
    if email_hash is not None:
        existing = db.scalar(select(Candidate).where(Candidate.email_hash == email_hash))
        if existing is not None:
            matched_on = "email"
    if existing is None and phone_hash is not None:
        existing = db.scalar(select(Candidate).where(Candidate.phone_hash == phone_hash))
        if existing is not None:
            matched_on = "phone"

    if existing is not None:
        return {
            "duplicate": True,
            "candidate_id": existing.id,
            "matched_on": matched_on,
            "possible_match_id": None,
        }

    # No strong match — look for a fuzzy name collision to flag (not merge).
    possible_id: int | None = None
    if name:
        for cand in db.scalars(select(Candidate)).all():
            if SequenceMatcher(None, name, _norm_name(cand.full_name)).ratio() >= _NAME_MATCH_THRESHOLD:
                possible_id = cand.id
                break

    new = Candidate(email_hash=email_hash, phone_hash=phone_hash, full_name=cv.get("full_name", ""))
    db.add(new)
    db.flush()  # assign id; caller's transaction commits
    return {
        "duplicate": False,
        "candidate_id": new.id,
        "matched_on": None,
        "possible_match_id": possible_id,
    }
