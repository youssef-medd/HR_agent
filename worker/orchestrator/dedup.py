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


def file_sha256(data: bytes) -> str:
    """Content hash of an uploaded file.

    Unsalted and unkeyed: this identifies a *document*, not a person, and has to
    be comparable across candidates. The salted `_hash` above is for PII.
    """
    return hashlib.sha256(data).hexdigest()


def find_duplicate_file(db: Session, job_id: int, digest: str) -> Any | None:
    """An earlier application to the same job carrying byte-identical bytes.

    Catches a re-upload before any parsing happens — the cheapest possible
    duplicate check, and it costs no LLM call.
    """
    from app.models.application import Application

    # `.as_string()` rather than `.astext`: the column is a JSON/JSONB variant,
    # so the postgresql-only accessor is not available on the generic type.
    return db.scalar(
        select(Application)
        .where(
            Application.job_id == job_id,
            Application.payload["cv_sha256"].as_string() == digest,
        )
        .order_by(Application.id.asc())
    )


# Fields where a later CV should win only if it actually says something. An
# empty value in the newer parse means "not mentioned this time", not "deleted".
_SCALAR_FIELDS = (
    "full_name", "email", "phone", "location", "summary", "language",
)
_LIST_FIELDS = ("skills", "languages", "certifications", "links")


# Two CVs describe the same certification differently — "AWS Certified Solutions
# Architect - Associate (2022)" vs "AWS Solutions Architect Associate (2022)".
# Exact matching keeps both, so the merged profile lists the same credential
# twice. Compare on a punctuation-stripped form, then fall back to similarity.
_LIST_ITEM_SIMILARITY = 0.85


def _list_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _same_item(a: str, b: str) -> bool:
    """Whether two list entries name the same thing."""
    if a == b:
        return True
    # An acronym and its expansion share no character similarity, but every word
    # of the short form appears in the long one: "ckad 2021" inside "certified
    # kubernetes application developer ckad 2021".
    short, long_ = sorted((a, b), key=len)
    short_words = short.split()
    if len(short_words) >= 2 and set(short_words) <= set(long_.split()):
        return True
    return SequenceMatcher(None, a, b).ratio() >= _LIST_ITEM_SIMILARITY


def _union_fuzzy(primary: list[Any], secondary: list[Any]) -> list[str]:
    """Union two lists, preferring `primary`'s wording, dropping near-duplicates.

    Requiring two words before treating containment as a match keeps "Java" and
    "JavaScript" apart — one is a substring of the other but they are different
    skills.
    """
    out: list[str] = []
    keys: list[str] = []
    for value in list(primary) + list(secondary):
        text = str(value).strip()
        key = _list_key(text)
        if not text or not key:
            continue
        if any(_same_item(key, k) for k in keys):
            continue
        keys.append(key)
        out.append(text)
    return out


def merge_profiles(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge an earlier parsed profile into the newer one — newest facts win.

    The same person re-applying with an updated CV should not lose history, and
    should not have a fresh fact overwritten by a stale one. So: the new value
    wins wherever it is non-empty, the old one fills gaps, lists are unioned
    (new first, order preserved), and experience/education entries absent from
    the newer document are appended rather than dropped.
    """
    merged = dict(new)

    for field in _SCALAR_FIELDS:
        if not str(new.get(field) or "").strip() and old.get(field):
            merged[field] = old[field]

    for field in _LIST_FIELDS:
        merged[field] = _union_fuzzy(
            list(new.get(field) or []), list(old.get(field) or [])
        )

    for field, key_fn in (
        ("experiences", lambda e: (str(e.get("company", "")).lower(), str(e.get("title", "")).lower())),
        ("education", lambda e: (str(e.get("institution", "")).lower(), str(e.get("degree", "")).lower())),
    ):
        new_entries = list(new.get(field) or [])
        known = {key_fn(e) for e in new_entries}
        for entry in old.get(field) or []:
            if key_fn(entry) not in known:
                new_entries.append(entry)
        merged[field] = new_entries

    if new.get("years_experience") is None and old.get("years_experience") is not None:
        merged["years_experience"] = old["years_experience"]

    return merged


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
