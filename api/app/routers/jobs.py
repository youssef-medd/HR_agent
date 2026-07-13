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

from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.user import User
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
