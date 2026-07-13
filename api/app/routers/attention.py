"""Needs-attention (human gate) queue endpoints.

Lists the open/resolved gate items with the candidate name resolved from the
linked application, and records recruiter decisions. Resolving a gate closes
the row (the audit surface `orchestrator.gates._assert_approved` checks) and
enqueues the orchestrator step so the paused LangGraph thread resumes with the
decision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.needs_attention import NeedsAttention
from app.models.user import User
from app.queue import enqueue_application_step
from app.security import require_role

router = APIRouter(prefix="/needs-attention", tags=["needs-attention"])


class AttentionItem(BaseModel):
    id: int
    application_id: int
    candidate_ref: str | None = None
    full_name: str | None = None
    reason: str
    gate: str | None = None
    context: dict[str, Any] = {}
    status: str
    created_at: str


@router.get("", response_model=list[AttentionItem])
def list_needs_attention(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[AttentionItem]:
    rows = db.scalars(
        select(NeedsAttention).order_by(NeedsAttention.created_at.desc())
    ).all()

    app_ids = {r.application_id for r in rows}
    apps = {
        a.id: a
        for a in db.scalars(
            select(Application).where(Application.id.in_(app_ids))
        ).all()
    }

    items: list[AttentionItem] = []
    for r in rows:
        app = apps.get(r.application_id)
        items.append(
            AttentionItem(
                id=r.id,
                application_id=r.application_id,
                candidate_ref=app.candidate_ref if app else None,
                full_name=((app.payload.get("cv") or {}).get("full_name") if app else None) or None,
                reason=r.reason,
                gate=r.gate,
                context=r.context or {},
                status=r.status,
                created_at=r.created_at.isoformat(),
            )
        )
    return items


class ResolveRequest(BaseModel):
    decision: Literal["approve", "reject"]


class ResolveResponse(BaseModel):
    id: int
    application_id: int
    status: str
    decision: str


@router.post("/{item_id}/resolve", response_model=ResolveResponse)
def resolve_gate(
    item_id: int,
    body: ResolveRequest,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> ResolveResponse:
    row = db.get(NeedsAttention, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    if row.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already resolved")

    row.status = "closed"
    row.resolved_by = user.email
    row.resolution = {"decision": body.decision}
    row.resolved_at = datetime.now(UTC)
    db.commit()

    # Resume the paused orchestrator thread with the recruiter's decision.
    if row.gate:
        enqueue_application_step(row.application_id, {"decision": body.decision})

    return ResolveResponse(
        id=row.id,
        application_id=row.application_id,
        status=row.status,
        decision=body.decision,
    )
