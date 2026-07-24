"""Public (unauthenticated) candidate endpoints.

The recruiter surface is entirely behind JWT auth; this router is the only
public one. It lets a candidate browse open roles and submit a CV without an
account. A submission creates the same `RECEIVED` application the recruiter
upload and the A3 email intake produce, so it merges into the identical
orchestrator pipeline (A1 parse → A4 score → …).

Only `published` jobs are visible/applyable — drafts and closed roles 404.
"""

from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.queue import enqueue_application_step

router = APIRouter(prefix="/public", tags=["public"])

_ALLOWED_EXT = (".pdf", ".docx", ".txt", ".md")
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class PublicJobView(BaseModel):
    id: int
    title: str
    department: str | None = None
    location: str | None = None
    description: str


class PublicApplicationCreated(BaseModel):
    application_id: int
    state: str


class TimelineEntry(BaseModel):
    state: str
    at: str


class TrackedApplication(BaseModel):
    id: int
    state: str
    job_title: str | None = None
    created_at: str
    timeline: list[TimelineEntry]


def _to_public(job: Job) -> PublicJobView:
    return PublicJobView(
        id=job.id,
        title=job.title,
        department=job.department,
        location=job.location,
        description=job.description,
    )


@router.get("/jobs", response_model=list[PublicJobView])
def list_open_jobs(db: Annotated[Session, Depends(get_db)]) -> list[PublicJobView]:
    jobs = db.scalars(
        select(Job).where(Job.status == "published").order_by(Job.id.desc())
    ).all()
    return [_to_public(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=PublicJobView)
def get_open_job(
    job_id: int, db: Annotated[Session, Depends(get_db)]
) -> PublicJobView:
    job = db.get(Job, job_id)
    if job is None or job.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _to_public(job)


@router.post(
    "/apply", response_model=PublicApplicationCreated, status_code=status.HTTP_201_CREATED
)
async def apply(
    db: Annotated[Session, Depends(get_db)],
    job_id: Annotated[int, Form()],
    email: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    full_name: Annotated[str | None, Form()] = None,
    phone: Annotated[str | None, Form()] = None,
) -> PublicApplicationCreated:
    job = db.get(Job, job_id)
    if job is None or job.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or not open"
        )

    filename = file.filename or "cv"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXT)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_BYTES // (1024 * 1024)} MB",
        )

    row = Application(
        job_id=job_id,
        candidate_ref=email,
        state="RECEIVED",
        payload={
            "cv_filename": filename,
            "cv_b64": base64.b64encode(data).decode("ascii"),
            "source": "web",
            "applicant_name": full_name or "",
            **({"phone": phone.strip()} if phone and phone.strip() else {}),
            **({"jd_text": job.description} if job.description else {}),
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_application_step(row.id)
    return PublicApplicationCreated(application_id=row.id, state=row.state)


@router.get("/track", response_model=TrackedApplication)
def track_application(
    email: str,
    application_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> TrackedApplication:
    """Candidate self-service tracking: status + timeline for one application.

    Identified by application id + the email it was submitted with (matched
    against `candidate_ref`, case-insensitive). A mismatch is a flat 404 so the
    endpoint never confirms which of the two was wrong.
    """
    row = db.get(Application, application_id)
    if row is None or row.candidate_ref.strip().lower() != email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No application found for that email and reference",
        )

    job = db.get(Job, row.job_id)
    events = db.scalars(
        select(ApplicationEvent)
        .where(
            ApplicationEvent.application_id == application_id,
            ApplicationEvent.kind == "transition",
        )
        .order_by(ApplicationEvent.created_at)
    ).all()
    timeline = [
        TimelineEntry(state=e.to_state, at=e.created_at.isoformat())
        for e in events
        if e.to_state
    ]

    return TrackedApplication(
        id=row.id,
        state=row.state,
        job_title=job.title if job is not None else None,
        created_at=row.created_at.isoformat(),
        timeline=timeline,
    )
