"""job spec column (A1)

Revision ID: 0004_job_spec
Revises: 0003_jobs
Create Date: 2026-07-24

A1 stores its structured output (JobSpec + weights + channel content) as JSONB
on the jobs row. Nullable — populated when the recruiter runs "Structure with AI".
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_job_spec"
down_revision = "0003_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "spec")
