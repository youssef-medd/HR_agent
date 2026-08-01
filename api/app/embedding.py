"""Shared text embedder (A4 semantic pre-rank + A8 handbook RAG).

Lives in `app.*` so both the API (handbook RAG endpoints) and the worker
(`orchestrator.semantic`) use one implementation.

Default embedder is a deterministic hashing vectorizer — no heavy dependency,
works offline, and gives sensible cosine similarity (texts sharing tokens score
higher). When `SEMANTIC_ENABLED` is set and `sentence-transformers` is
installed, `SEMANTIC_MODEL` (default `BAAI/bge-m3`) is used instead. All vectors
are L2-normalized `EMBED_DIM`-vectors so cosine == dot product.
"""

from __future__ import annotations

import hashlib
import math
import os
import re

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
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")  # noqa: S324
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
    """Embed texts to unit vectors — bge-m3 when enabled+installed, else hashing."""
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
