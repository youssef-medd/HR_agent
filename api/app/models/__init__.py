"""ORM models.

Import every model here so that `Base.metadata` sees them when Alembic runs
autogenerate and when tests spin up a schema.
"""

from __future__ import annotations

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.audit_log import AuditLog
from app.models.candidate import Candidate
from app.models.esco_skill import EscoSkill
from app.models.idempotency_ledger import IdempotencyLedger
from app.models.job import Job
from app.models.message_log import MessageLog
from app.models.needs_attention import NeedsAttention
from app.models.onboarding_task import OnboardingTask
from app.models.report_snapshot import ReportSnapshot
from app.models.sourced_profile import SourcedProfile
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationEvent",
    "AuditLog",
    "Candidate",
    "EscoSkill",
    "IdempotencyLedger",
    "Job",
    "MessageLog",
    "NeedsAttention",
    "OnboardingTask",
    "ReportSnapshot",
    "SourcedProfile",
    "User",
]
