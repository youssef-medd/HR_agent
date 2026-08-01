"""A2 — sourced candidate tracking.

One row per person a recruiter sources for a job. This is the record that stops
the same person being contacted twice, tracks which outreach draft was used,
and links through to the application once the profile is imported into the
pipeline.

Outreach itself stays manual (LinkedIn-assist — nothing is auto-sent); this
table records what the recruiter did.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SourcedProfile(Base):
    __tablename__ = "sourced_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Public profile URL (LinkedIn/GitHub/…). Used to detect a repeat contact.
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="linkedin")
    # sourced | contacted | replied | imported | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="sourced", index=True)
    outreach_tone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set once the profile has been pushed into the pipeline as an application.
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
