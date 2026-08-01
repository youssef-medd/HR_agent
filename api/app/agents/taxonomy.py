"""A1 — skill normalization against the ESCO taxonomy table.

Maps each extracted skill to its canonical taxonomy label (exact then fuzzy);
skills with no close match are kept verbatim so nothing is lost.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.esco_skill import EscoSkill

_FUZZY_THRESHOLD = 0.9


def _load(db: Session) -> list[tuple[str, str]]:
    """(normalized, canonical label) pairs from the taxonomy."""
    return [(s.normalized, s.label) for s in db.scalars(select(EscoSkill)).all()]


def normalize_skill(raw: str, taxonomy: list[tuple[str, str]]) -> str:
    key = raw.strip().lower()
    if not key:
        return raw
    for norm, label in taxonomy:
        if norm == key:
            return label
    best_label, best_score = raw, 0.0
    for norm, label in taxonomy:
        score = SequenceMatcher(None, key, norm).ratio()
        if score > best_score:
            best_label, best_score = label, score
    return best_label if best_score >= _FUZZY_THRESHOLD else raw


def normalize_skills(db: Session, skills: list[str]) -> list[str]:
    """Canonicalise a list of skills against the taxonomy, de-duplicating."""
    if not skills:
        return []
    taxonomy = _load(db)
    if not taxonomy:
        return list(skills)
    out: list[str] = []
    seen: set[str] = set()
    for s in skills:
        canonical = normalize_skill(s, taxonomy)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            out.append(canonical)
    return out
