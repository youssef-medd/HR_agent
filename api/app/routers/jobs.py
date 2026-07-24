"""Job posting endpoints.

Jobs carry the description/requirements text A4 scores against. External
publication (job boards) passes through a human gate later (spec §7); for now
`status` moves between draft/published/closed without side effects.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.job_intake import JobIntake, structure_job
from app.agents.sourcer import SourcingKit, generate_sourcing_kit
from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.user import User
from app.queue import enqueue_application_step
from app.security import require_role

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
) -> SourcingKit:
    """A2 — generate a recruiter sourcing kit (boolean search + outreach draft)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return generate_sourcing_kit(
        title=job.title,
        description=job.description,
        department=job.department,
        location=job.location,
        user_id=str(user.id),
    )


@router.post("/{job_id}/structure", response_model=JobIntake)
def job_structure(
    job_id: int,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
) -> JobIntake:
    """A1 — structure a raw JD into a JobSpec + weights + channel content, stored on the job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    result = structure_job(title=job.title, raw_jd=job.description, user_id=str(user.id))
    job.spec = result.model_dump()
    db.commit()
    return result


class ProfileImport(BaseModel):
    raw_text: str = Field(min_length=1, max_length=40000)
    full_name: str | None = None
    candidate_ref: str | None = None


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

    enqueue_application_step(row.id)
    return ImportedApplication(application_id=row.id, state=row.state)
