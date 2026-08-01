"""A4 stage 2 — semantic matching features.

Embeds JobSpec sections and the candidate profile, then turns cosine
similarities (skills↔requirements, experience↔missions) into pre-ranking
features the judge/dashboard can order a batch by (best first).

Embedder is pluggable:

- Default: a deterministic hashing vectorizer — no heavy dependency, works
  offline, and gives sensible similarity (texts sharing tokens score higher).
  This keeps the feature layer usable and unit-testable everywhere.
- Real model: when `SEMANTIC_ENABLED` is set and `sentence-transformers` is
  installed, `SEMANTIC_MODEL` (default `BAAI/bge-m3`) is loaded and used.

Embeddings are L2-normalized `EMBED_DIM`-vectors so cosine == dot product.
Persistence in pgvector lives in `orchestrator.embeddings`.
"""

from __future__ import annotations

from typing import Any

# The embedder is shared with the API (app.embedding) so both services use one
# implementation (A4 pre-rank + A8 handbook RAG).
from app.embedding import EMBED_DIM, cosine, embed, semantic_enabled

__all__ = ["EMBED_DIM", "cosine", "embed", "semantic_enabled", "semantic_features"]


def _join(*parts: Any) -> str:
    out: list[str] = []
    for p in parts:
        if isinstance(p, list):
            out.extend(str(x) for x in p)
        elif p:
            out.append(str(p))
    return " ".join(out)


def semantic_features(job_spec: dict[str, Any], cv: dict[str, Any]) -> dict[str, float]:
    """Cosine pre-ranking features between a JobSpec and a candidate profile.

    Returns skills_sim, experience_sim, and prerank_score (their mean) in
    [0, 1]. `job_spec` is A1's `spec` block; `cv` is the parsed CVData dict.
    """
    spec = job_spec or {}
    req_text = _join(spec.get("must_have"), spec.get("nice_to_have"), spec.get("missions"))
    missions_text = _join(spec.get("missions"), spec.get("seniority"))
    skills_text = _join(cv.get("skills"), cv.get("summary"))
    exp_text = _join(
        [e.get("title", "") + " " + e.get("summary", "") for e in cv.get("experiences", [])]
    )

    vectors = embed([req_text, missions_text, skills_text, exp_text])
    req_v, missions_v, skills_v, exp_v = vectors
    skills_sim = max(0.0, cosine(skills_v, req_v))
    experience_sim = max(0.0, cosine(exp_v, missions_v))
    return {
        "skills_sim": round(skills_sim, 4),
        "experience_sim": round(experience_sim, 4),
        "prerank_score": round((skills_sim + experience_sim) / 2, 4),
    }
