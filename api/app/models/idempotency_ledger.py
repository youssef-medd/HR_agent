"""Idempotency ledger.

Every side-effecting step in the orchestrator writes exactly one row keyed by
(application_id, step, attempt). Replays hit this ledger first: if a previous
attempt already succeeded, the recorded result is returned and the effect is
skipped. This is what makes "kill mid-batch, restart, zero duplicates" true.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class IdempotencyLedger(Base):
    __tablename__ = "idempotency_ledger"
    __table_args__ = (UniqueConstraint("application_id", "step", "attempt", name="uq_ledger_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    result: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
