"""Candidate identity (A3 dedup).

A candidate is a person; an application is one submission by that person for a
job. A3 deduplicates incoming CVs against this table by hashed email/phone so
repeat applicants (across jobs or channels) attach to the same candidate rather
than spawning a new identity each time.

Only salted hashes of contact details are stored here, never the raw email or
phone — the raw values live on the (erasable) application payload.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
