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
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
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


@router.post("", response_model=ApplicationCreated, status_code=status.HTTP_201_CREATED)
async def create_application(
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
    db: Annotated[Session, Depends(get_db)],
    job_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    candidate_ref: Annotated[str | None, Form()] = None,
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

    row = Application(
        job_id=job_id,
        candidate_ref=candidate_ref or filename,
        state="RECEIVED",
        payload={
            "cv_filename": filename,
            "cv_b64": base64.b64encode(data).decode("ascii"),
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_application_step(row.id)

    return ApplicationCreated(application_id=row.id, state=row.state)


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
