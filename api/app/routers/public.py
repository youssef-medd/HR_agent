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
from app.models.onboarding_task import OnboardingTask
from app.queue import enqueue_application_step
from app.rgpd import erase_candidate

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


# --- A5 web-chat pre-screening (candidate portal channel) -------------------

_AWAITING_STATUSES = {"awaiting_consent", "asking"}


class PrescreenMessage(BaseModel):
    role: str
    text: str


class PrescreenView(BaseModel):
    state: str
    status: str
    channel: str
    transcript: list[PrescreenMessage]
    awaiting: bool  # the assistant is waiting on the candidate's reply
    done: bool


class PrescreenReplyIn(BaseModel):
    email: str
    application_id: int
    message: str


def _verify_candidate(db: Session, application_id: int, email: str) -> Application:
    row = db.get(Application, application_id)
    if row is None or row.candidate_ref.strip().lower() != email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No application found for that email and reference",
        )
    return row


@router.get("/prescreen", response_model=PrescreenView)
def prescreen_view(
    email: str,
    application_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PrescreenView:
    """Candidate's web pre-screening chat: transcript + whose turn it is."""
    row = _verify_candidate(db, application_id, email)
    block = (row.payload.get("prescreen") or {}) if isinstance(row.payload, dict) else {}
    status_str = block.get("status") or ""
    transcript = [
        PrescreenMessage(role=m.get("role", ""), text=m.get("text", ""))
        for m in (block.get("transcript") or [])
    ]
    done = row.state != "PRESCREENING" or status_str == "done"
    awaiting = row.state == "PRESCREENING" and status_str in _AWAITING_STATUSES
    return PrescreenView(
        state=row.state,
        status=status_str,
        channel=block.get("channel") or "web",
        transcript=transcript,
        awaiting=awaiting,
        done=done,
    )


@router.post("/prescreen/reply", response_model=PrescreenView)
def prescreen_reply(
    body: PrescreenReplyIn,
    db: Annotated[Session, Depends(get_db)],
) -> PrescreenView:
    """Candidate answers in the web chat — resumes the paused A5 graph."""
    row = _verify_candidate(db, body.application_id, body.email)
    if row.state != "PRESCREENING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is not awaiting a pre-screening reply",
        )
    enqueue_application_step(body.application_id, {"candidate_message": body.message})
    return prescreen_view(email=body.email, application_id=body.application_id, db=db)


# --- A6 web interview booking (candidate portal channel) --------------------


class BookingView(BaseModel):
    state: str
    link: str
    awaiting: bool  # PRESCREENED and waiting on the candidate to book
    booked: bool
    when: str | None = None


class BookingConfirmIn(BaseModel):
    email: str
    application_id: int
    slot: str | None = None


@router.get("/booking", response_model=BookingView)
def booking_view(
    email: str,
    application_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> BookingView:
    """A6 web booking: the Cal.com link + whether the candidate still needs to book."""
    row = _verify_candidate(db, application_id, email)
    interview = (row.payload.get("interview") or {}) if isinstance(row.payload, dict) else {}
    return BookingView(
        state=row.state,
        link=interview.get("link") or "",
        awaiting=row.state == "PRESCREENED",
        booked=bool(interview.get("booked")) or row.state == "INTERVIEW_SCHEDULED",
        when=interview.get("when"),
    )


@router.post("/booking/confirm", response_model=BookingView)
def booking_confirm(
    body: BookingConfirmIn,
    db: Annotated[Session, Depends(get_db)],
) -> BookingView:
    """Candidate confirms a booked slot from the portal — resumes the paused A6 graph."""
    row = _verify_candidate(db, body.application_id, body.email)
    if row.state != "PRESCREENED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is not awaiting an interview booking",
        )
    when = body.slot or "the proposed time"
    enqueue_application_step(
        body.application_id, {"candidate_message": f"I booked the interview for {when}."}
    )
    return booking_view(email=body.email, application_id=body.application_id, db=db)


# --- RGPD erasure (spec §7 — candidate right to be forgotten) ----------------


class EraseIn(BaseModel):
    email: str
    application_id: int


class EraseView(BaseModel):
    erased: bool
    applications_erased: int


@router.post("/candidates/erase", response_model=EraseView)
def erase_candidate_data(
    body: EraseIn,
    db: Annotated[Session, Depends(get_db)],
) -> EraseView:
    """Anonymise all of a candidate's data after verifying ownership.

    The candidate proves ownership with one application's email+reference; every
    application under that reference is then anonymised (audit trail retained,
    personal data scrubbed)."""
    row = _verify_candidate(db, body.application_id, body.email)
    count = erase_candidate(db, row.candidate_ref, reason="candidate_request")
    return EraseView(erased=True, applications_erased=count)


# --- A8 onboarding: candidate document upload portal -------------------------


class OnbTaskView(BaseModel):
    id: int
    category: str
    label: str
    status: str
    due_at: str | None
    uploaded: bool


class OnboardingView(BaseModel):
    state: str
    tasks: list[OnbTaskView]
    documents_total: int
    documents_received: int
    complete: bool


def _onboarding_view(db: Session, row: Application) -> OnboardingView:
    tasks = db.scalars(
        select(OnboardingTask).where(OnboardingTask.application_id == row.id)
        .order_by(OnboardingTask.category, OnboardingTask.id)
    ).all()
    docs = [t for t in tasks if t.category == "document"]
    received = [t for t in docs if t.status in ("received", "done")]
    return OnboardingView(
        state=row.state,
        tasks=[
            OnbTaskView(
                id=t.id, category=t.category, label=t.label, status=t.status,
                due_at=t.due_at.isoformat() if t.due_at else None,
                uploaded=t.uploaded_ref is not None,
            )
            for t in tasks
        ],
        documents_total=len(docs),
        documents_received=len(received),
        complete=bool(docs) and len(received) == len(docs),
    )


@router.get("/onboarding", response_model=OnboardingView)
def onboarding_view(
    email: str,
    application_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingView:
    """The candidate's onboarding checklist + document-collection progress."""
    row = _verify_candidate(db, application_id, email)
    return _onboarding_view(db, row)


@router.post("/onboarding/upload", response_model=OnboardingView)
async def onboarding_upload(
    db: Annotated[Session, Depends(get_db)],
    email: Annotated[str, Form()],
    application_id: Annotated[int, Form()],
    task_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
) -> OnboardingView:
    """Candidate uploads one required document; marks its task received."""
    row = _verify_candidate(db, application_id, email)
    task = db.get(OnboardingTask, task_id)
    if task is None or task.application_id != row.id or task.category != "document":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document task not found")

    filename = file.filename or "upload"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXT)}",
        )
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_BYTES // (1024 * 1024)} MB",
        )
    # File-store integration (MinIO) lands later; for now record the filename ref
    # and mark the document received so collection progress advances.
    task.uploaded_ref = filename
    task.status = "received"
    db.commit()
    return _onboarding_view(db, row)
