"""A7 — outbound message log.

Every candidate-facing message (email or WhatsApp) is recorded here on send:
the rendered body actually delivered, the template it came from, the channel,
and the delivery status. This is the audit surface for messaging integrity
(spec §6 A7) and the source the per-candidate rate-limiter reads to decide
whether a new message is allowed.

Append-only. `status` is one of: sent (provider accepted), stub (no transport
configured — recorded only), skipped_rate_limited (suppressed by the limiter),
failed (transport raised).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MessageLog(Base):
    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=True, index=True
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # email | whatsapp
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rendered_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent")
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
