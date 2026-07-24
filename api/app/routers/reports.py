"""A9 — reporting & analytics.

Aggregates the recruitment funnel from the append-only application-event log
(`orchestrator` writes a `transition` event on every state change) plus the
current application rows. Returns per-stage reach + conversion rates, a
time-in-funnel SLA (average hours from RECEIVED to each stage), the average
judge score, and a per-job breakdown — the numbers the diagram's dotted A9
node feeds on.

Read-only; available to any authenticated role.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.needs_attention import NeedsAttention
from app.models.user import User
from app.security import require_role

router = APIRouter(prefix="/reports", tags=["reports"])

# Ordered happy-path funnel. RECEIVED is the entry (all applications); the rest
# are reached via a transition event into that state.
_FUNNEL = [
    "RECEIVED",
    "PARSED",
    "SCORED",
    "SHORTLISTED",
    "PRESCREENED",
    "INTERVIEW_SCHEDULED",
    "HIRED",
]


class FunnelStage(BaseModel):
    stage: str
    reached: int
    rate_from_prev: float  # 0..1, share of the previous stage that reached this one
    avg_hours_from_received: float | None


class JobFunnel(BaseModel):
    job_id: int
    title: str
    applicants: int
    shortlisted: int


class ReportOverview(BaseModel):
    total_applications: int
    by_state: dict[str, int]
    by_source: dict[str, int]
    funnel: list[FunnelStage]
    avg_score: float | None
    shortlist_rate: float
    hire_rate: float
    open_gates: int
    per_job: list[JobFunnel]


@router.get("/overview", response_model=ReportOverview)
def overview(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> ReportOverview:
    apps = db.scalars(select(Application)).all()
    total = len(apps)

    by_state: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for a in apps:
        by_state[a.state] = by_state.get(a.state, 0) + 1
        src = (a.payload.get("source") or "upload") if isinstance(a.payload, dict) else "upload"
        by_source[src] = by_source.get(src, 0) + 1

    # Earliest transition into each state, per application, from the event log.
    events = db.execute(
        select(
            ApplicationEvent.application_id,
            ApplicationEvent.to_state,
            ApplicationEvent.created_at,
        ).where(ApplicationEvent.kind == "transition")
    ).all()

    reached_ids: dict[str, set[int]] = {}
    first_at: dict[tuple[int, str], datetime] = {}
    for app_id, to_state, created in events:
        if not to_state:
            continue
        reached_ids.setdefault(to_state, set()).add(app_id)
        key = (app_id, to_state)
        if key not in first_at or created < first_at[key]:
            first_at[key] = created

    created_at = {a.id: a.created_at for a in apps}

    funnel: list[FunnelStage] = []
    prev_reached: int | None = None
    for stage in _FUNNEL:
        reached = total if stage == "RECEIVED" else len(reached_ids.get(stage, set()))

        if prev_reached is None:
            rate = 1.0
        elif prev_reached > 0:
            rate = reached / prev_reached
        else:
            rate = 0.0

        deltas: list[float] = []
        if stage != "RECEIVED":
            for app_id in reached_ids.get(stage, set()):
                at = first_at.get((app_id, stage))
                start = created_at.get(app_id)
                if at and start:
                    deltas.append((at - start).total_seconds() / 3600.0)
        avg_hours = round(sum(deltas) / len(deltas), 2) if deltas else None

        funnel.append(
            FunnelStage(
                stage=stage,
                reached=reached,
                rate_from_prev=round(rate, 4),
                avg_hours_from_received=avg_hours,
            )
        )
        prev_reached = reached

    # Average judge score across applications that have been scored.
    scores = [
        s["overall"]
        for a in apps
        if isinstance((s := a.payload.get("score")), dict) and s.get("overall") is not None
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    shortlisted_ids = reached_ids.get("SHORTLISTED", set())
    hired_ids = reached_ids.get("HIRED", set())
    shortlist_rate = round(len(shortlisted_ids) / total, 4) if total else 0.0
    hire_rate = round(len(hired_ids) / total, 4) if total else 0.0

    open_gates = (
        db.query(NeedsAttention).filter(NeedsAttention.status == "open").count()
    )

    jobs = {j.id: j for j in db.scalars(select(Job)).all()}
    per: dict[int, dict[str, int]] = {}
    for a in apps:
        d = per.setdefault(a.job_id, {"applicants": 0, "shortlisted": 0})
        d["applicants"] += 1
        if a.id in shortlisted_ids:
            d["shortlisted"] += 1
    per_job = [
        JobFunnel(
            job_id=jid,
            title=jobs[jid].title if jid in jobs else f"Job #{jid}",
            applicants=d["applicants"],
            shortlisted=d["shortlisted"],
        )
        for jid, d in sorted(per.items())
    ]

    return ReportOverview(
        total_applications=total,
        by_state=by_state,
        by_source=by_source,
        funnel=funnel,
        avg_score=avg_score,
        shortlist_rate=shortlist_rate,
        hire_rate=hire_rate,
        open_gates=open_gates,
        per_job=per_job,
    )
