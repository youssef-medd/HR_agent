"""A8 — company handbook ingest + grounded Q&A endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.handbook import HandbookAnswer, answer_question, ingest_handbook
from app.db import get_db
from app.models.user import User
from app.security import require_role

router = APIRouter(prefix="/handbook", tags=["onboarding"])


class IngestIn(BaseModel):
    source: str
    body: str


class IngestResult(BaseModel):
    source: str
    chunks: int


class AskIn(BaseModel):
    question: str


@router.post("/ingest", response_model=IngestResult)
def ingest(
    body: IngestIn,
    user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> IngestResult:
    """Ingest a company handbook document (admin only)."""
    n = ingest_handbook(db, body.source, body.body)
    return IngestResult(source=body.source, chunks=n)


@router.post("/ask", response_model=HandbookAnswer)
def ask(
    body: AskIn,
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> HandbookAnswer:
    """Answer a handbook question, grounded in the ingested content or refused."""
    return answer_question(db, body.question, user_id=str(user.id))
