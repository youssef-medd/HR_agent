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

import csv
import io
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.message_log import MessageLog
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
    avg_score: float | None = None
    # Score distribution buckets for THIS job (spec §A9: distributions par offre).
    score_buckets: dict[str, int] = {}


class SourceConversion(BaseModel):
    applied: int
    shortlisted: int
    hired: int
    shortlist_rate: float
    hire_rate: float


class ReportOverview(BaseModel):
    total_applications: int
    by_state: dict[str, int]
    by_source: dict[str, int]
    # Source efficiency: conversion by acquisition source (incl. linkedin_assist).
    source_conversion: dict[str, SourceConversion]
    funnel: list[FunnelStage]
    avg_score: float | None
    # Overall score distribution across all scored applications.
    score_distribution: dict[str, int]
    shortlist_rate: float
    hire_rate: float
    open_gates: int
    per_job: list[JobFunnel]


# Score bucket labels, low -> high (spec verdict bands informed the edges).
_SCORE_BUCKETS = [("0-44", 0, 45), ("45-69", 45, 70), ("70-84", 70, 85), ("85-100", 85, 101)]


def _bucket(score: int) -> str:
    for label, lo, hi in _SCORE_BUCKETS:
        if lo <= score < hi:
            return label
    return _SCORE_BUCKETS[-1][0]


@router.get("/overview", response_model=ReportOverview)
def overview(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> ReportOverview:
    return compute_overview(db)


def compute_overview(db: Session) -> ReportOverview:
    """The A9 KPI aggregation — shared by the live endpoint and the beat jobs."""
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

    # Overall score distribution + per-job scores/buckets.
    score_distribution: dict[str, int] = {label: 0 for label, _, _ in _SCORE_BUCKETS}
    jobs = {j.id: j for j in db.scalars(select(Job)).all()}
    per: dict[int, dict[str, Any]] = {}
    for a in apps:
        d = per.setdefault(
            a.job_id,
            {"applicants": 0, "shortlisted": 0, "scores": [], "buckets": {}},
        )
        d["applicants"] += 1
        if a.id in shortlisted_ids:
            d["shortlisted"] += 1
        s = a.payload.get("score") if isinstance(a.payload, dict) else None
        overall = s.get("overall") if isinstance(s, dict) else None
        if overall is not None:
            b = _bucket(int(overall))
            score_distribution[b] += 1
            d["scores"].append(int(overall))
            d["buckets"][b] = d["buckets"].get(b, 0) + 1

    per_job = [
        JobFunnel(
            job_id=jid,
            title=jobs[jid].title if jid in jobs else f"Job #{jid}",
            applicants=d["applicants"],
            shortlisted=d["shortlisted"],
            avg_score=round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else None,
            score_buckets=d["buckets"],
        )
        for jid, d in sorted(per.items())
    ]

    # Source efficiency: conversion by acquisition source.
    src_conv: dict[str, dict[str, int]] = {}
    for a in apps:
        source = str(a.payload.get("source") or "upload") if isinstance(a.payload, dict) else "upload"
        s = src_conv.setdefault(source, {"applied": 0, "shortlisted": 0, "hired": 0})
        s["applied"] += 1
        if a.id in shortlisted_ids:
            s["shortlisted"] += 1
        if a.id in hired_ids:
            s["hired"] += 1
    source_conversion = {
        source: SourceConversion(
            applied=v["applied"], shortlisted=v["shortlisted"], hired=v["hired"],
            shortlist_rate=round(v["shortlisted"] / v["applied"], 4) if v["applied"] else 0.0,
            hire_rate=round(v["hired"] / v["applied"], 4) if v["applied"] else 0.0,
        )
        for source, v in sorted(src_conv.items())
    }

    return ReportOverview(
        total_applications=total,
        by_state=by_state,
        by_source=by_source,
        source_conversion=source_conversion,
        funnel=funnel,
        avg_score=avg_score,
        score_distribution=score_distribution,
        shortlist_rate=shortlist_rate,
        hire_rate=hire_rate,
        open_gates=open_gates,
        per_job=per_job,
    )


class MessagingSummary(BaseModel):
    total: int
    by_channel: dict[str, int]
    by_status: dict[str, int]
    by_template: dict[str, int]
    rate_limited: int


@router.get("/messaging", response_model=MessagingSummary)
def messaging_summary(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> MessagingSummary:
    """A7/A9 — outbound message stats from the message_log audit table.

    Note: token/cost-per-hire is intentionally not computed here — the platform
    does not persist per-generation token counts locally (they live in Langfuse,
    spec §3). Wire it to the Langfuse API when cost reporting is required rather
    than approximating it from message counts.
    """
    def _counts(column) -> dict[str, int]:
        rows = db.execute(select(column, func.count()).group_by(column)).all()
        return {str(k): int(v) for k, v in rows}

    total = db.execute(select(func.count()).select_from(MessageLog)).scalar_one()
    by_status = _counts(MessageLog.status)
    return MessagingSummary(
        total=int(total),
        by_channel=_counts(MessageLog.channel),
        by_status=by_status,
        by_template=_counts(MessageLog.template_id),
        rate_limited=by_status.get("skipped_rate_limited", 0),
    )


class MessageRow(BaseModel):
    id: int
    application_id: int | None
    recipient: str
    channel: str
    template_id: str | None
    status: str
    body: str
    created_at: str


@router.get("/messages", response_model=list[MessageRow])
def message_center(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
) -> list[MessageRow]:
    """A7 message center — the most recent logged outbound messages."""
    rows = db.scalars(
        select(MessageLog).order_by(MessageLog.created_at.desc()).limit(min(limit, 500))
    ).all()
    return [
        MessageRow(
            id=m.id,
            application_id=m.application_id,
            recipient=m.recipient,
            channel=m.channel,
            template_id=m.template_id,
            status=m.status,
            body=(m.rendered_body or "")[:2000],
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in rows
    ]


_CSV_COLUMNS = [
    "id", "job_id", "job_title", "candidate_ref", "state", "source",
    "score_overall", "recommendation", "created_at",
]


@router.get("/applications.csv")
def applications_csv(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """A9 — export all applications as CSV (admin/recruiter only)."""
    jobs = {j.id: j.title for j in db.scalars(select(Job)).all()}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)
    for a in db.scalars(select(Application).order_by(Application.id)).all():
        payload = a.payload if isinstance(a.payload, dict) else {}
        raw_score = payload.get("score")
        score = raw_score if isinstance(raw_score, dict) else {}
        writer.writerow([
            a.id,
            a.job_id,
            jobs.get(a.job_id, f"Job #{a.job_id}"),
            a.candidate_ref,
            a.state,
            payload.get("source") or "upload",
            score.get("overall", ""),
            score.get("recommendation", ""),
            a.created_at.isoformat() if a.created_at else "",
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )
