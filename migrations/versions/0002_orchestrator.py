"""orchestrator tables

Revision ID: 0002_orchestrator
Revises: 0001_users
Create Date: 2026-07-09

Adds the tables owned by A0 (spec §2.1, §7):
    - applications
    - application_events (append-only)
    - audit_log (append-only, cross-cutting)
    - needs_attention_queue
    - idempotency_ledger

LangGraph's own checkpoint tables (`checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`) are provisioned by `PostgresSaver.setup()` on worker
boot; they are intentionally not managed by Alembic.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_orchestrator"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("candidate_ref", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="RECEIVED"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_candidate_ref", "applications", ["candidate_ref"])
    op.create_index("ix_applications_state", "applications", ["state"])

    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column("step", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_application_events_application_id", "application_events", ["application_id"])
    op.create_index("ix_application_events_kind", "application_events", ["kind"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_subject_id", "audit_log", ["subject_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.create_table(
        "needs_attention_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("gate", sa.String(length=64), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_needs_attention_application_id", "needs_attention_queue", ["application_id"])
    op.create_index("ix_needs_attention_reason", "needs_attention_queue", ["reason"])
    op.create_index("ix_needs_attention_status", "needs_attention_queue", ["status"])
    op.create_index("ix_needs_attention_created_at", "needs_attention_queue", ["created_at"])

    op.create_table(
        "idempotency_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("application_id", "step", "attempt", name="uq_ledger_key"),
    )
    op.create_index("ix_idempotency_ledger_application_id", "idempotency_ledger", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_ledger_application_id", table_name="idempotency_ledger")
    op.drop_table("idempotency_ledger")

    for ix in (
        "ix_needs_attention_created_at",
        "ix_needs_attention_status",
        "ix_needs_attention_reason",
        "ix_needs_attention_application_id",
    ):
        op.drop_index(ix, table_name="needs_attention_queue")
    op.drop_table("needs_attention_queue")

    for ix in (
        "ix_audit_log_created_at",
        "ix_audit_log_subject_id",
        "ix_audit_log_action",
        "ix_audit_log_actor",
    ):
        op.drop_index(ix, table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_application_events_kind", table_name="application_events")
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")

    op.drop_index("ix_applications_state", table_name="applications")
    op.drop_index("ix_applications_candidate_ref", table_name="applications")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_table("applications")
