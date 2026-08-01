"""A8 — tracked onboarding checklist rows.

When an application reaches HIRED, A8 generates an onboarding kit and persists
each item here so the checklist can be tracked to completion: documents the
candidate must upload, accounts/equipment to provision, and week-one agenda
items. Document rows drive the collection-progress + reminder/escalation logic.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OnboardingTask(Base):
    __tablename__ = "onboarding_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # document | account | equipment | agenda
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # pending | received | done | expired
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # For document tasks: reference to the uploaded file (filename on payload store).
    uploaded_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
