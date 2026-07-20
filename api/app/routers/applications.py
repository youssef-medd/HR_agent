"""Application intake endpoints.

`POST /applications` is the entry point a recruiter uses to submit a CV. The
file is stored (base64 on the row's payload for now — MinIO object storage is
a later iteration) and the orchestrator is triggered, which runs A1 (parse)
and the rest of the pipeline. `GET /applications/{id}` returns the row plus the
parsed CV so the caller can watch it progress.
"""

from __future__ import annotations

import base64
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.onboarder import OnboardingKit, generate_onboarding_kit
from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.user import User
from app.queue import enqueue_application_step
from app.security import require_role

router = APIRouter(prefix="/applications", tags=["applications"])

_ALLOWED_EXT = (".pdf", ".docx", ".txt", ".md")
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class ApplicationCreated(BaseModel):
    application_id: int
    state: str


class ApplicationView(BaseModel):
    id: int
    job_id: int
    candidate_ref: str
    state: str
    cv: dict[str, Any] | None = None


class ApplicationSummary(BaseModel):
    id: int
    job_id: int
    candidate_ref: str
    state: str
    full_name: str | None = None
    score: int | None = None
    recommendation: str | None = None
    created_at: str


@router.post("", response_model=ApplicationCreated, status_code=status.HTTP_201_CREATED)
async def create_application(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    job_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    candidate_ref: Annotated[str | None, Form()] = None,
    job_description: Annotated[str | None, Form()] = None,
) -> ApplicationCreated:
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

    # Explicit job_description wins; otherwise inherit the job posting's text
    # so A4 scores against the stored requirements.
    jd_text = job_description
    if not jd_text:
        job = db.get(Job, job_id)
        if job is not None and job.description:
            jd_text = job.description

    row = Application(
        job_id=job_id,
        candidate_ref=candidate_ref or filename,
        state="RECEIVED",
        payload={
            "cv_filename": filename,
            "cv_b64": base64.b64encode(data).decode("ascii"),
            **({"jd_text": jd_text} if jd_text else {}),
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_application_step(row.id)

    return ApplicationCreated(application_id=row.id, state=row.state)


@router.get("", response_model=list[ApplicationSummary])
def list_applications(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[ApplicationSummary]:
    rows = db.scalars(select(Application).order_by(Application.id.desc())).all()
    return [
        ApplicationSummary(
            id=r.id,
            job_id=r.job_id,
            candidate_ref=r.candidate_ref,
            state=r.state,
            full_name=(r.payload.get("cv") or {}).get("full_name") or None,
            score=(r.payload.get("score") or {}).get("overall"),
            recommendation=(r.payload.get("score") or {}).get("recommendation"),
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


class PrescreenReply(BaseModel):
    message: str


class PrescreenReplyAccepted(BaseModel):
    application_id: int
    state: str


@router.post("/{application_id}/prescreen/reply", response_model=PrescreenReplyAccepted)
def prescreen_reply(
    application_id: int,
    body: PrescreenReply,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> PrescreenReplyAccepted:
    """Deliver a candidate's pre-screening reply into the paused A5 conversation.

    Stub inbound path — a real Meta WhatsApp Cloud API webhook replaces this
    later. Resumes the LangGraph thread exactly the way a recruiter gate
    decision does (see needs-attention resolve): enqueue an orchestrator step
    carrying the message, which feeds the node's `interrupt()`.
    """
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if row.state != "PRESCREENING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application is not awaiting a pre-screening reply",
        )

    enqueue_application_step(application_id, {"candidate_message": body.message})
    return PrescreenReplyAccepted(application_id=application_id, state=row.state)


@router.post("/{application_id}/interview/booking", response_model=PrescreenReplyAccepted)
def interview_booking_reply(
    application_id: int,
    body: PrescreenReply,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> PrescreenReplyAccepted:
    """Deliver a candidate's interview-booking reply into the paused A6 step.

    Stub inbound path — a real Cal.com booking webhook replaces this later.
    Resumes the LangGraph thread the same way the pre-screening reply does; the
    application rests at PRESCREENED while the schedule node awaits the booking.
    """
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if row.state != "PRESCREENED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application is not awaiting an interview booking",
        )

    enqueue_application_step(application_id, {"candidate_message": body.message})
    return PrescreenReplyAccepted(application_id=application_id, state=row.state)


@router.get("/{application_id}", response_model=ApplicationView)
def get_application(
    application_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationView:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return ApplicationView(
        id=row.id,
        job_id=row.job_id,
        candidate_ref=row.candidate_ref,
        state=row.state,
        cv=row.payload.get("cv"),
    )


@router.post("/{application_id}/onboarding", response_model=OnboardingKit)
def application_onboarding(
    application_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingKit:
    """A8 — generate an onboarding kit for a hired candidate (checklist, week-1 plan)."""
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    job = db.get(Job, row.job_id)
    role_title = job.title if job is not None else "New role"
    department = job.department if job is not None else None
    candidate_name = (row.payload.get("cv") or {}).get("full_name") or None

    return generate_onboarding_kit(
        role_title=role_title,
        department=department,
        candidate_name=candidate_name,
        user_id=str(user.id),
    )
