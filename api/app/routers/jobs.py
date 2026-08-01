"""Job posting endpoints.

Jobs carry the description/requirements text A4 scores against. External
publication (job boards) passes through a human gate later (spec §7); for now
`status` moves between draft/published/closed without side effects.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.job_intake import (
    GUIDED_QUESTIONS,
    IntakeTurn,
    JobIntake,
    brief_from_answers,
    converse_intake,
    structure_job,
)
from app.agents.sourcer import SourcingKit, generate_sourcing_kit
from app.agents.taxonomy import normalize_skills
from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.sourced_profile import SourcedProfile
from app.models.user import User
from app.queue import enqueue_application_step
from app.security import require_role

router = APIRouter(prefix="/jobs", tags=["jobs"])

_JD_EXT = (".pdf", ".docx", ".txt", ".md")
_MAX_JD_BYTES = 10 * 1024 * 1024  # 10 MB


def _tracking_link(job_id: int) -> str:
    base = (os.environ.get("PORTAL_URL") or "http://localhost:3001").rstrip("/")
    return f"{base}/apply/{job_id}?src=careers"


def _extract_jd_text(filename: str, data: bytes) -> str:
    """Plain text from an uploaded JD (PDF/DOCX/txt)."""
    name = filename.lower()
    if name.endswith(".pdf"):
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc).strip()
    if name.endswith(".docx"):
        import io

        from docx import Document

        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs).strip()
    return data.decode("utf-8", errors="replace").strip()


class JobCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    department: str | None = None
    location: str | None = None
    description: str = Field(default="", max_length=20000)
    status: str = Field(default="published", pattern="^(draft|published|closed)$")


class JobView(BaseModel):
    id: int
    title: str
    department: str | None
    location: str | None
    description: str
    status: str
    created_at: str
    applicants: int = 0
    shortlisted: int = 0
    spec: dict | None = None


def _to_view(job: Job, applicants: int = 0, shortlisted: int = 0) -> JobView:
    return JobView(
        id=job.id,
        title=job.title,
        department=job.department,
        location=job.location,
        description=job.description,
        status=job.status,
        created_at=job.created_at.isoformat(),
        applicants=applicants,
        shortlisted=shortlisted,
        spec=job.spec,
    )


@router.post("", response_model=JobView, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> JobView:
    job = Job(
        title=body.title,
        department=body.department,
        location=body.location,
        description=body.description,
        status=body.status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_view(job)


@router.get("", response_model=list[JobView])
def list_jobs(
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[JobView]:
    jobs = db.scalars(select(Job).order_by(Job.id.desc())).all()

    counts = {
        job_id: (total, shortlisted)
        for job_id, total, shortlisted in db.execute(
            select(
                Application.job_id,
                func.count(Application.id),
                func.count(Application.id).filter(Application.state == "SHORTLISTED"),
            ).group_by(Application.job_id)
        ).all()
    }

    return [
        _to_view(j, *(counts.get(j.id, (0, 0))))
        for j in jobs
    ]


@router.get("/{job_id}", response_model=JobView)
def get_job(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter", "viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> JobView:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _to_view(job)


@router.post("/{job_id}/sourcing", response_model=SourcingKit)
def job_sourcing(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    refresh: bool = False,
) -> SourcingKit:
    """A2 — the recruiter sourcing kit (boolean search + outreach drafts).

    Cached on the job: reopening the panel returns the stored kit instead of
    burning another LLM call. Pass `refresh=true` to regenerate. Consumes A1's
    structured spec when present, so the search strings use the real must-haves.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.sourcing and not refresh:
        return SourcingKit.model_validate(job.sourcing)

    kit = generate_sourcing_kit(
        title=job.title,
        description=job.description,
        department=job.department,
        location=job.location,
        spec=job.spec,
        user_id=str(user.id),
    )
    job.sourcing = kit.model_dump()
    db.commit()
    return kit


# --- A2 sourced-profile tracking --------------------------------------------


class SourcedProfileIn(BaseModel):
    full_name: str = Field(default="", max_length=255)
    profile_url: str | None = None
    platform: str = Field(default="linkedin", max_length=32)
    outreach_tone: str | None = None
    notes: str | None = None


class SourcedProfileView(BaseModel):
    id: int
    job_id: int
    full_name: str
    profile_url: str | None
    platform: str
    status: str
    outreach_tone: str | None
    notes: str | None
    application_id: int | None
    contacted_at: str | None
    created_at: str


class SourcedProfileUpdate(BaseModel):
    status: str | None = None
    outreach_tone: str | None = None
    notes: str | None = None


def _sourced_view(row: SourcedProfile) -> SourcedProfileView:
    return SourcedProfileView(
        id=row.id,
        job_id=row.job_id,
        full_name=row.full_name,
        profile_url=row.profile_url,
        platform=row.platform,
        status=row.status,
        outreach_tone=row.outreach_tone,
        notes=row.notes,
        application_id=row.application_id,
        contacted_at=row.contacted_at.isoformat() if row.contacted_at else None,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.get("/{job_id}/sourced", response_model=list[SourcedProfileView])
def list_sourced(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> list[SourcedProfileView]:
    """A2 — everyone sourced for this job, newest first."""
    rows = db.scalars(
        select(SourcedProfile)
        .where(SourcedProfile.job_id == job_id)
        .order_by(SourcedProfile.created_at.desc())
    ).all()
    return [_sourced_view(r) for r in rows]


@router.post(
    "/{job_id}/sourced", response_model=SourcedProfileView, status_code=status.HTTP_201_CREATED
)
def add_sourced(
    job_id: int,
    body: SourcedProfileIn,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> SourcedProfileView:
    """A2 — record a sourced person.

    Refuses a duplicate profile URL for the same job (409) so the recruiter
    never contacts the same candidate twice.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    url = (body.profile_url or "").strip().rstrip("/") or None
    if url:
        existing = db.scalar(
            select(SourcedProfile).where(
                SourcedProfile.job_id == job_id, SourcedProfile.profile_url == url
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Already sourced for this job ({existing.status})",
            )

    row = SourcedProfile(
        job_id=job_id,
        full_name=body.full_name.strip(),
        profile_url=url,
        platform=body.platform,
        outreach_tone=body.outreach_tone,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _sourced_view(row)


@router.patch("/sourced/{sourced_id}", response_model=SourcedProfileView)
def update_sourced(
    sourced_id: int,
    body: SourcedProfileUpdate,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> SourcedProfileView:
    """A2 — update a sourced person (mark contacted, add notes)."""
    row = db.get(SourcedProfile, sourced_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sourced profile not found")
    if body.status is not None:
        row.status = body.status
        if body.status == "contacted" and row.contacted_at is None:
            row.contacted_at = datetime.now(UTC)
    if body.outreach_tone is not None:
        row.outreach_tone = body.outreach_tone
    if body.notes is not None:
        row.notes = body.notes
    db.commit()
    db.refresh(row)
    return _sourced_view(row)


class StructureIn(BaseModel):
    # Any one of: a free-text brief/prompt, the six guided answers; else the job
    # description is used.
    brief: str | None = None
    answers: dict[str, str] | None = None


def _persist_intake(db: Session, job: Job, result: JobIntake) -> JobIntake:
    # Normalize extracted skills against the ESCO taxonomy (spec §A1 pipeline).
    result.spec.must_have = normalize_skills(db, result.spec.must_have)
    result.spec.nice_to_have = normalize_skills(db, result.spec.nice_to_have)
    result.tracking_link = _tracking_link(job.id)
    job.spec = result.model_dump()
    db.commit()
    return result


@router.get("/intake/questions")
def intake_questions(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
) -> list[dict[str, str]]:
    """A1 — the six guided-intake questions for the 'answer questions' input mode."""
    return GUIDED_QUESTIONS


class ChatIntakeIn(BaseModel):
    messages: list[dict[str, str]] = Field(default_factory=list)
    title: str | None = None


@router.post("/intake/converse", response_model=IntakeTurn)
def intake_converse_new(
    body: ChatIntakeIn,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
) -> IntakeTurn:
    """A1 — from-scratch conversational intake (no job yet). The AI asks the next
    question or, when ready, proposes a title + full spec. Nothing is saved here;
    the recruiter confirms via /intake/create."""
    return converse_intake(body.title or "", body.messages, user_id=str(user.id))


class ExtractResult(BaseModel):
    filename: str
    text: str
    chars: int


@router.post("/intake/extract", response_model=ExtractResult)
async def intake_extract(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    file: Annotated[UploadFile, File()],
) -> ExtractResult:
    """A1 — extract text from an uploaded JD (PDF/DOCX/txt) with no job yet.

    Lets the conversational intake accept a job-description file: the extracted
    text is fed into the chat as the recruiter's brief."""
    filename = file.filename or "jd"
    if not filename.lower().endswith(_JD_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_JD_EXT)}",
        )
    data = await file.read()
    if len(data) > _MAX_JD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_JD_BYTES // (1024 * 1024)} MB",
        )
    try:
        text = _extract_jd_text(filename, data)
    except Exception as exc:  # noqa: BLE001 — surface a clean 422 to the UI
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read {filename}: {exc}",
        ) from exc
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted (is it a scanned PDF?)",
        )
    return ExtractResult(filename=filename, text=text, chars=len(text))


class ChatCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    intake: JobIntake


class ChatCreateResult(BaseModel):
    job_id: int
    intake: JobIntake


@router.post("/intake/create", response_model=ChatCreateResult)
def intake_create(
    body: ChatCreateIn,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> ChatCreateResult:
    """A1 — create the job from a confirmed AI draft (recruiter said 'finalize')."""
    spec = body.intake.spec
    description = "\n".join(spec.missions)
    if spec.must_have:
        description += "\n\nRequired: " + ", ".join(spec.must_have)
    job = Job(
        title=body.title,
        location=spec.location or None,
        description=description.strip() or body.title,
        status="published",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    intake = _persist_intake(db, job, body.intake)
    return ChatCreateResult(job_id=job.id, intake=intake)


@router.post("/{job_id}/structure", response_model=JobIntake)
def job_structure(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    body: Annotated[StructureIn | None, Body()] = None,
) -> JobIntake:
    """A1 — structure a JD into a JobSpec + weights + channels + tracking link.

    Input (priority): the six guided `answers`, else a free-text `brief`/prompt,
    else the stored job description."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if body and body.answers:
        raw = brief_from_answers(job.title, body.answers)
    elif body and body.brief:
        raw = body.brief
    else:
        raw = job.description or ""

    result = structure_job(title=job.title, raw_jd=raw, user_id=str(user.id))
    return _persist_intake(db, job, result)


class ConverseIn(BaseModel):
    messages: list[dict[str, str]] = Field(default_factory=list)


@router.post("/{job_id}/intake/converse", response_model=IntakeTurn)
def job_intake_converse(
    job_id: int,
    body: ConverseIn,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> IntakeTurn:
    """A1 conversational intake — the AI asks the next clarifying question, or
    finalizes the spec (persisted when done)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    turn = converse_intake(job.title, body.messages, user_id=str(user.id))
    if turn.done and turn.intake is not None:
        turn.intake = _persist_intake(db, job, turn.intake)
    return turn


@router.post("/{job_id}/structure/upload", response_model=JobIntake)
async def job_structure_upload(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> JobIntake:
    """A1 — structure from an uploaded JD file (PDF / DOCX / txt)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    filename = file.filename or "jd"
    if not filename.lower().endswith(_JD_EXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(_JD_EXT)}",
        )
    text = _extract_jd_text(filename, await file.read())
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No text could be extracted from the file")
    result = structure_job(title=job.title, raw_jd=text, user_id=str(user.id))
    return _persist_intake(db, job, result)


@router.patch("/{job_id}/spec", response_model=JobIntake)
def job_spec_override(
    job_id: int,
    body: JobIntake,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> JobIntake:
    """A1 — save recruiter edits to the structured spec as an override (spec §A1 AC)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    body.overridden = True
    if not body.tracking_link:
        body.tracking_link = _tracking_link(job_id)
    job.spec = body.model_dump()
    db.commit()
    return body


class ProfileImport(BaseModel):
    raw_text: str = Field(min_length=1, max_length=40000)
    full_name: str | None = None
    candidate_ref: str | None = None
    # Optional link back to the tracked sourced person (marks them imported).
    sourced_id: int | None = None


class ImportedApplication(BaseModel):
    application_id: int
    state: str


@router.post(
    "/{job_id}/import-profile",
    response_model=ImportedApplication,
    status_code=status.HTTP_201_CREATED,
)
def import_profile(
    job_id: int,
    body: ProfileImport,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> ImportedApplication:
    """A2 — import a sourced profile (pasted text) as a scored application.

    The recruiter runs the search manually and pastes the public profile text
    here; it flows through the same pipeline as an uploaded CV (A3 parse -> A4
    score), tagged `source=linkedin_assist`.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    row = Application(
        job_id=job_id,
        candidate_ref=body.candidate_ref or body.full_name or "sourced-profile",
        state="RECEIVED",
        payload={
            "cv_text": body.raw_text,
            "source": "linkedin_assist",
            "applicant_name": body.full_name or "",
            **({"jd_text": job.description} if job.description else {}),
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Close the loop on the tracked sourced person, if this came from one.
    if body.sourced_id is not None:
        sourced = db.get(SourcedProfile, body.sourced_id)
        if sourced is not None and sourced.job_id == job_id:
            sourced.status = "imported"
            sourced.application_id = row.id
            db.commit()

    enqueue_application_step(row.id)
    return ImportedApplication(application_id=row.id, state=row.state)
