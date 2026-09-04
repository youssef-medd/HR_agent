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
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.cv_prefill import CVPrefill, prefill_from_text
from app.db import get_db
from app.interviews import (
    InterviewError,
    block_of,
    book_slot,
    format_slot,
    parse_slot,
    reschedule,
)
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from app.models.onboarding_task import OnboardingTask
from app.portal_token import PortalTokenError, make_portal_token, read_portal_token
from app.queue import enqueue_application_step, enqueue_portal_link
from app.rgpd import erase_candidate
from app.textract import extract_text

router = APIRouter(prefix="/public", tags=["public"])

# Images are accepted for both entry points that use this: a photographed CV
# (A3 OCRs it) and an onboarding document, where a phone photo of an ID or a
# RIB is the normal case.
_ALLOWED_EXT = (
    ".pdf", ".docx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
)
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class PublicJobView(BaseModel):
    id: int
    title: str
    department: str | None = None
    location: str | None = None
    description: str
    # A curated slice of A1's JobSpec, for the public job page. Deliberately
    # excludes `eliminatory_criteria` and `weights` — those are internal
    # screening logic and must not be visible to candidates, who would
    # otherwise know exactly what to claim.
    seniority: str = ""
    missions: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


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
    # Echoed back so a candidate arriving on a token link (who never typed an
    # address) can still drive the chat/booking/onboarding panels, which
    # identify by email. Only ever returned after verification, and only the
    # candidate's own address.
    email: str = ""


def _to_public(job: Job) -> PublicJobView:
    # A1 stores the structured intake as {"spec": {...}, "weights": {...},
    # "channels": {...}}; a job that has never been structured has spec=None.
    spec = ((job.spec or {}).get("spec")) or {}

    def _list(key: str) -> list[str]:
        val = spec.get(key)
        return [str(v) for v in val] if isinstance(val, list) else []

    return PublicJobView(
        id=job.id,
        title=job.title,
        department=job.department,
        location=job.location or str(spec.get("location") or "") or None,
        description=job.description,
        seniority=str(spec.get("seniority") or ""),
        missions=_list("missions"),
        must_have=_list("must_have"),
        nice_to_have=_list("nice_to_have"),
        languages=_list("languages"),
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
    link: Annotated[str | None, Form()] = None,
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
            # A LinkedIn/portfolio URL the candidate gives us directly. Kept
            # separate from the CV's own `links`, which A3 extracts.
            **({"applicant_link": link.strip()} if link and link.strip() else {}),
            **({"jd_text": job.description} if job.description else {}),
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_application_step(row.id)
    return PublicApplicationCreated(application_id=row.id, state=row.state)


@router.post("/prefill", response_model=CVPrefill)
async def prefill_application(
    file: Annotated[UploadFile, File()],
) -> CVPrefill:
    """Read name/email/phone/LinkedIn out of a CV so the form fills itself.

    Called when the candidate attaches their file, before they submit. Nothing
    is stored and no application is created — this only reads the document and
    hands the fields straight back to the browser that supplied it.

    Every failure returns empty fields rather than an error: the candidate can
    always type the details, so a bad parse must not block them.
    """
    filename = file.filename or "cv"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXT)}",
        )
    data = await file.read()
    if not data or len(data) > _MAX_BYTES:
        return CVPrefill()

    try:
        text = extract_text(filename, data)
    except Exception:  # noqa: BLE001 — an unreadable CV just means no prefill
        return CVPrefill()
    return prefill_from_text(text)


class PortalLinkIn(BaseModel):
    email: str


class PortalLinkSent(BaseModel):
    sent: bool


@router.post("/portal/request-link", response_model=PortalLinkSent)
def request_portal_link(
    body: PortalLinkIn,
    db: Annotated[Session, Depends(get_db)],
) -> PortalLinkSent:
    """Email the candidate a signed link to every application under that address.

    This is what removes the reference number from the candidate's memory: the
    proof of identity is access to the inbox, not a number they wrote down.

    Always reports `sent: true`, whether or not the address has applied —
    otherwise the endpoint becomes an oracle for "has this person applied
    here", which is exactly the disclosure §7 forbids.
    """
    address = body.email.strip().lower()
    rows = db.scalars(
        select(Application)
        .where(func.lower(Application.candidate_ref) == address)
        .order_by(Application.id.desc())
    ).all()

    if rows:
        base = (os.environ.get("PORTAL_URL") or "http://localhost:3001").rstrip("/")
        links = []
        for row in rows:
            job = db.get(Job, row.job_id)
            links.append(
                {
                    "title": job.title if job is not None else f"Application #{row.id}",
                    "url": f"{base}/portal?t={make_portal_token(row.id, row.candidate_ref)}",
                }
            )
        # Best-effort: a queue failure must not change the response, or its
        # shape would leak whether the address exists.
        try:
            enqueue_portal_link(address, links)
        except Exception:  # noqa: BLE001
            pass

    return PortalLinkSent(sent=True)


@router.get("/track", response_model=TrackedApplication)
def track_application(
    db: Annotated[Session, Depends(get_db)],
    email: str = "",
    application_id: int = 0,
    token: str | None = None,
) -> TrackedApplication:
    """Candidate self-service tracking: status + timeline for one application.

    Identified by a signed portal token, or by application id + the email it was
    submitted with (matched against `candidate_ref`, case-insensitive). A
    mismatch is a flat 404 so the endpoint never confirms which was wrong.
    """
    row = _verify_candidate(db, application_id, email, token)

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
        email=row.candidate_ref,
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
    email: str = ""
    application_id: int = 0
    message: str
    # Signed portal token; supersedes email + application_id.
    token: str | None = None



def _verify_candidate(
    db: Session,
    application_id: int | None,
    email: str | None,
    token: str | None = None,
) -> Application:
    """Resolve a candidate to their application, by signed token or email+ref.

    The token is the primary credential (spec §7): it is unguessable, where the
    raw `application_id` is sequential and therefore walkable by anyone who
    knows the candidate's email. Email + reference is retained as a fallback for
    a candidate whose emailed link has expired or who never received it.

    Both paths fail with the same 404 and the same message — distinguishing
    "wrong reference" from "no such application" would confirm which emails
    have applied.
    """
    if token:
        try:
            application_id, email = read_portal_token(token)
        except PortalTokenError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That link is invalid or has expired. Request a new one.",
            ) from None

    row = db.get(Application, application_id) if application_id else None
    if row is None or row.candidate_ref.strip().lower() != (email or "").strip().lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No application found for that email and reference",
        )
    return row


@router.get("/prescreen", response_model=PrescreenView)
def prescreen_view(
    db: Annotated[Session, Depends(get_db)],
    email: str = "",
    application_id: int = 0,
    token: str | None = None,
) -> PrescreenView:
    """Candidate's web pre-screening chat: transcript + whose turn it is."""
    row = _verify_candidate(db, application_id, email, token)
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
    row = _verify_candidate(db, body.application_id, body.email, body.token)
    if row.state != "PRESCREENING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is not awaiting a pre-screening reply",
        )
    enqueue_application_step(body.application_id, {"candidate_message": body.message})
    return prescreen_view(email=body.email, application_id=body.application_id, db=db)


# --- A6 web interview booking (candidate portal channel) --------------------


class BookingSlot(BaseModel):
    at: str  # ISO-8601 UTC
    label: str  # rendered in the candidate's timezone


class BookingView(BaseModel):
    state: str
    link: str
    awaiting: bool  # PRESCREENED and waiting on the candidate to book
    booked: bool
    when: str | None = None
    scheduled_at: str | None = None
    timezone: str = "UTC"
    slots: list[BookingSlot] = Field(default_factory=list)
    can_reschedule: bool = False
    no_show: bool = False
    reschedule_count: int = 0


class BookingConfirmIn(BaseModel):
    email: str = ""
    application_id: int = 0
    # The exact slot the candidate picked, ISO-8601. Free-text `slot` is kept as
    # a fallback for a candidate who booked elsewhere (Cal.com page) and is only
    # telling us about it.
    slot_at: str | None = None
    slot: str | None = None
    # Signed portal token; supersedes email + application_id.
    token: str | None = None


class BookingRescheduleIn(BookingConfirmIn):
    reason: str | None = None


def _booking_slots(block: dict) -> list[BookingSlot]:
    """Proposed slots, dropping any that has already elapsed."""
    now = datetime.now(UTC)
    tz = block.get("timezone") or "UTC"
    out: list[BookingSlot] = []
    for raw in block.get("proposed_slots") or []:
        try:
            start = parse_slot(str(raw))
        except ValueError:
            continue
        if start <= now:
            continue
        out.append(BookingSlot(at=start.isoformat(), label=format_slot(start, tz)))
    return out


def _resolve_slot(block: dict, body: BookingConfirmIn) -> datetime | None:
    """The concrete start time the candidate picked, if they gave one."""
    if not body.slot_at:
        return None
    try:
        return parse_slot(body.slot_at)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid slot timestamp",
        ) from None


@router.get("/booking", response_model=BookingView)
def booking_view(
    db: Annotated[Session, Depends(get_db)],
    email: str = "",
    application_id: int = 0,
    token: str | None = None,
) -> BookingView:
    """A6 web booking: proposed slots, the booking link, and the current booking."""
    row = _verify_candidate(db, application_id, email, token)
    interview = (row.payload.get("interview") or {}) if isinstance(row.payload, dict) else {}
    return BookingView(
        state=row.state,
        link=interview.get("link") or "",
        awaiting=row.state == "PRESCREENED",
        booked=bool(interview.get("booked")) or row.state == "INTERVIEW_SCHEDULED",
        when=interview.get("when"),
        scheduled_at=interview.get("scheduled_at"),
        timezone=interview.get("timezone") or "UTC",
        slots=_booking_slots(interview),
        can_reschedule=row.state == "INTERVIEW_SCHEDULED",
        no_show=bool(interview.get("no_show")),
        reschedule_count=int(interview.get("reschedule_count") or 0),
    )


@router.post("/booking/confirm", response_model=BookingView)
def booking_confirm(
    body: BookingConfirmIn,
    db: Annotated[Session, Depends(get_db)],
) -> BookingView:
    """Candidate picks a slot from the portal — resumes the paused A6 graph.

    The chosen start time is stamped on the row *before* the graph is resumed, so
    `schedule_node` builds the ICS for the slot the candidate actually picked
    rather than falling back to the first proposed one.
    """
    row = _verify_candidate(db, body.application_id, body.email, body.token)
    if row.state != "PRESCREENED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is not awaiting an interview booking",
        )
    block = block_of(row)
    start = _resolve_slot(block, body)
    when = body.slot or "the proposed time"
    if start is not None:
        block = book_slot(db, row, start=start, source="portal")
        when = block.get("when") or when
    enqueue_application_step(
        row.id, {"candidate_message": f"I booked the interview for {when}."}
    )
    return booking_view(email=body.email, application_id=row.id, db=db, token=body.token)


@router.post("/booking/reschedule", response_model=BookingView)
def booking_reschedule(
    body: BookingRescheduleIn,
    db: Annotated[Session, Depends(get_db)],
) -> BookingView:
    """Candidate moves an already booked interview to another slot.

    No graph resume: the application is past A6 and parked on the A7 offer gate,
    so the new time is written here and a replacement calendar invite (same UID,
    bumped SEQUENCE) is queued for the worker to send.
    """
    row = _verify_candidate(db, body.application_id, body.email, body.token)
    start = _resolve_slot(block_of(row), body)
    if start is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pick a new slot to reschedule to",
        )
    if start <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That slot is in the past",
        )
    try:
        reschedule(db, row, start=start, source="portal", reason=body.reason)
    except InterviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return booking_view(email=body.email, application_id=row.id, db=db, token=body.token)


# --- RGPD erasure (spec §7 — candidate right to be forgotten) ----------------


class EraseIn(BaseModel):
    email: str = ""
    application_id: int = 0
    # Signed portal token; supersedes email + application_id.
    token: str | None = None



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
    row = _verify_candidate(db, body.application_id, body.email, body.token)
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
    db: Annotated[Session, Depends(get_db)],
    email: str = "",
    application_id: int = 0,
    token: str | None = None,
) -> OnboardingView:
    """The candidate's onboarding checklist + document-collection progress."""
    row = _verify_candidate(db, application_id, email, token)
    return _onboarding_view(db, row)


@router.post("/onboarding/upload", response_model=OnboardingView)
async def onboarding_upload(
    db: Annotated[Session, Depends(get_db)],
    task_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    email: Annotated[str, Form()] = "",
    application_id: Annotated[int, Form()] = 0,
    # Multipart, so the token arrives as a form field rather than a query param.
    token: Annotated[str | None, Form()] = None,
) -> OnboardingView:
    """Candidate uploads one required document; marks its task received."""
    row = _verify_candidate(db, application_id, email, token)
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
