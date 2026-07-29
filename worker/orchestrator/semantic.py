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

import hashlib
import math
import os
import re
from typing import Any

EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
_TOKEN_RE = re.compile(r"[a-zA-Z0-9\+\#\.]+")


def semantic_enabled() -> bool:
    return os.environ.get("SEMANTIC_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def _hash_embed(text: str) -> list[float]:
    """Deterministic hashing vectorizer -> L2-normalized EMBED_DIM vector."""
    vec = [0.0] * EMBED_DIM
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")  # noqa: S324 - not security
        idx = h % EMBED_DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


_model = None


def _real_embed(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # heavy, optional

        _model = SentenceTransformer(os.environ.get("SEMANTIC_MODEL", "BAAI/bge-m3"))
    return [list(map(float, v)) for v in _model.encode(texts, normalize_embeddings=True)]


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts to unit vectors. Uses bge-m3 when enabled+installed, else the
    deterministic hashing vectorizer."""
    if not texts:
        return []
    if semantic_enabled():
        try:
            return _real_embed(texts)
        except Exception:  # noqa: BLE001 - fall back to the offline embedder
            pass
    return [_hash_embed(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (dot product for unit vectors)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    return max(-1.0, min(1.0, dot))


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
