"""ORM models.

Import every model here so that `Base.metadata` sees them when Alembic runs
autogenerate and when tests spin up a schema.
"""

from __future__ import annotations

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.audit_log import AuditLog
from app.models.idempotency_ledger import IdempotencyLedger
from app.models.job import Job
from app.models.needs_attention import NeedsAttention
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationEvent",
    "AuditLog",
    "IdempotencyLedger",
    "Job",
    "NeedsAttention",
    "User",
]
