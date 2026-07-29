"""A4 stage 2 — pgvector embedding persistence + batch pre-ranking.

Stores a candidate profile embedding per application in the pgvector
`application_embeddings` table and ranks a job's applicants by cosine distance
to a query text. Postgres-only: guarded by the session dialect so the sqlite
test path (and any non-Postgres deployment) simply no-ops.

Uses raw SQL with pgvector's string literal cast (`'[...]'::vector`) so the ORM
models loaded in tests never need the Vector column type.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from orchestrator.semantic import EMBED_DIM, embed, semantic_features


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _vec_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def _profile_text(cv: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(str(s) for s in cv.get("skills", []))
    parts.append(str(cv.get("summary", "")))
    parts.extend(
        f"{e.get('title', '')} {e.get('summary', '')}" for e in cv.get("experiences", [])
    )
    return " ".join(p for p in parts if p.strip())


def store_application_embedding(db: Session, application_id: int, cv: dict[str, Any]) -> bool:
    """Embed the profile and upsert it into pgvector. No-op off Postgres."""
    if not _is_postgres(db):
        return False
    vector = embed([_profile_text(cv)])[0]
    db.execute(
        text(
            "INSERT INTO application_embeddings (application_id, embedding) "
            "VALUES (:aid, CAST(:emb AS vector)) "
            "ON CONFLICT (application_id) DO UPDATE SET embedding = EXCLUDED.embedding"
        ),
        {"aid": application_id, "emb": _vec_literal(vector)},
    )
    return True


def prerank_applications(db: Session, job_id: int, query_text: str, limit: int = 50) -> list[int]:
    """Application ids for a job, ordered best-first by cosine similarity to
    `query_text` (typically the JobSpec). Empty off Postgres."""
    if not _is_postgres(db):
        return []
    qvec = embed([query_text])[0]
    rows = db.execute(
        text(
            "SELECT a.id FROM applications a "
            "JOIN application_embeddings e ON e.application_id = a.id "
            "WHERE a.job_id = :jid "
            "ORDER BY e.embedding <=> CAST(:q AS vector) "
            "LIMIT :lim"
        ),
        {"jid": job_id, "q": _vec_literal(qvec), "lim": limit},
    ).all()
    return [r[0] for r in rows]


# Re-exported so callers can build a job query vector consistently.
__all__ = ["EMBED_DIM", "prerank_applications", "semantic_features", "store_application_embedding"]
