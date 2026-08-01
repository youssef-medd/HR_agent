"""onboarding_tasks + handbook_chunks (A8)

Revision ID: 0009_onboarding_tasks
Revises: 0008_report_snapshots
Create Date: 2026-07-30

A8: tracked onboarding checklist rows (document collection, accounts, agenda)
and a pgvector-backed handbook chunk store for the grounded Q&A assistant.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_onboarding_tasks"
down_revision = "0008_report_snapshots"
branch_labels = None
depends_on = None

_DIM = 1024


def upgrade() -> None:
    op.create_table(
        "onboarding_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id", sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_ref", sa.Text(), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_onboarding_tasks_application_id", "onboarding_tasks", ["application_id"])
    op.create_index("ix_onboarding_tasks_category", "onboarding_tasks", ["category"])
    op.create_index("ix_onboarding_tasks_status", "onboarding_tasks", ["status"])

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS handbook_chunks (
            id SERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector({_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS handbook_chunks")
    op.drop_index("ix_onboarding_tasks_status", table_name="onboarding_tasks")
    op.drop_index("ix_onboarding_tasks_category", table_name="onboarding_tasks")
    op.drop_index("ix_onboarding_tasks_application_id", table_name="onboarding_tasks")
    op.drop_table("onboarding_tasks")
