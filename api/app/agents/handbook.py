"""A8 — company handbook RAG assistant.

Ingest: chunk the handbook text, embed each chunk (bge-m3 when enabled, else the
hashing embedder), and store in the pgvector `handbook_chunks` table. Query:
embed the question, retrieve the nearest chunks by cosine distance, and answer
with the judge model **grounded only in those chunks**, citing the source. When
nothing relevant is retrieved (best similarity below a floor), the assistant
refuses with an "I don't know" rather than hallucinating a policy.

pgvector is Postgres-only; retrieval is guarded by the session dialect so the
sqlite test path exercises the chunking/citation/refusal logic with an injected
retriever.
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.embedding import embed
from app.gateway import llm_call

PROMPT_VERSION = "handbook@v1"
MIN_SIMILARITY = float(os.environ.get("HANDBOOK_MIN_SIM", "0.15"))
REFUSAL = "I don't have that information in the company handbook."


def chunk_text(text_in: str, *, target: int = 600) -> list[str]:
    """Split handbook text into ~`target`-char chunks on paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text_in or "") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if buf and len(buf) + len(p) + 1 > target:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def _vec_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def ingest_handbook(db: Session, source: str, body: str) -> int:
    """Chunk + embed + store the handbook. Replaces any prior chunks for `source`.
    Returns the number of chunks stored. No-op off Postgres."""
    if not _is_postgres(db):
        return 0
    chunks = chunk_text(body)
    vectors = embed(chunks)
    db.execute(text("DELETE FROM handbook_chunks WHERE source = :s"), {"s": source})
    for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=False)):
        db.execute(
            text(
                "INSERT INTO handbook_chunks (source, ordinal, content, embedding) "
                "VALUES (:s, :o, :c, CAST(:e AS vector))"
            ),
            {"s": source, "o": i, "c": chunk, "e": _vec_literal(vec)},
        )
    db.commit()
    return len(chunks)


def _retrieve(db: Session, question: str, k: int) -> list[dict[str, Any]]:
    """Nearest handbook chunks with a cosine *similarity* (1 - distance). Empty
    off Postgres."""
    if not _is_postgres(db):
        return []
    qvec = embed([question])[0]
    rows = db.execute(
        text(
            "SELECT source, ordinal, content, "
            "1 - (embedding <=> CAST(:q AS vector)) AS similarity "
            "FROM handbook_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": _vec_literal(qvec), "k": k},
    ).all()
    return [
        {"source": r[0], "ordinal": r[1], "content": r[2], "similarity": float(r[3])}
        for r in rows
    ]


class HandbookAnswer(BaseModel):
    answer: str = Field(default="")
    grounded: bool = Field(default=False)
    citations: list[str] = Field(default_factory=list)


_SYSTEM = (
    "You are an onboarding assistant answering ONLY from the provided company "
    "handbook excerpts. Rules: use ONLY the excerpts; never invent a policy. If "
    "the excerpts do not contain the answer, reply EXACTLY with the refusal text "
    "given. Cite the source of each fact you use by its [source] tag. Respond "
    'with a JSON object {"answer": string, "grounded": boolean, "citations": '
    "[source tags]}. Nothing else."
)


def answer_question(
    db: Session, question: str, *, k: int = 4, retriever=_retrieve, user_id: str | None = None
) -> HandbookAnswer:
    """Answer a handbook question grounded in retrieved chunks, or refuse."""
    hits = retriever(db, question, k)
    relevant = [h for h in hits if h["similarity"] >= MIN_SIMILARITY]
    if not relevant:
        return HandbookAnswer(answer=REFUSAL, grounded=False, citations=[])

    context = "\n\n".join(f"[{h['source']}#{h['ordinal']}]\n{h['content']}" for h in relevant)
    user_content = (
        f"HANDBOOK EXCERPTS:\n{context}\n\nQUESTION: {question}\n\n"
        f'If not answerable from the excerpts, set grounded=false and answer="{REFUSAL}".'
    )
    try:
        result: HandbookAnswer = llm_call(
            profile="judge",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_content},
            ],
            schema=HandbookAnswer,
            user_id=user_id,
            metadata={"agent": "A8", "prompt_version": PROMPT_VERSION, "stage": "handbook_qa"},
        )
    except ValidationError:
        return HandbookAnswer(answer=REFUSAL, grounded=False, citations=[])
    return result
