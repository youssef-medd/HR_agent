"""Needs-attention (human gate) queue endpoints.

Read-only for now: lists the open and resolved gate items with the candidate
name resolved from the linked application. The resolution endpoints (approve /
reject a gate, resuming the orchestrator thread) land with sprint 3.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.needs_attention import NeedsAttention
from app.models.user import User
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
