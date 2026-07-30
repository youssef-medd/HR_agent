"""A9 — nightly KPI aggregate snapshot.

The nightly beat job writes one row here with the full overview metrics as of
that run, so trends can be charted without recomputing history from the raw
event log every time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    metrics: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
