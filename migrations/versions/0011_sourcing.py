"""jobs.sourcing cache + sourced_profiles (A2)

Revision ID: 0011_sourcing
Revises: 0010_esco_skills
Create Date: 2026-08-01

A2: cache the generated sourcing kit on the job (so reopening the panel does
not burn another LLM call) and track every sourced person per job — the record
that prevents contacting the same candidate twice.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_sourcing"
down_revision = "0010_esco_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("sourcing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "sourced_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="linkedin"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="sourced"),
        sa.Column("outreach_tone", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sourced_profiles_job_id", "sourced_profiles", ["job_id"])
    op.create_index("ix_sourced_profiles_profile_url", "sourced_profiles", ["profile_url"])
    op.create_index("ix_sourced_profiles_status", "sourced_profiles", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sourced_profiles_status", table_name="sourced_profiles")
    op.drop_index("ix_sourced_profiles_profile_url", table_name="sourced_profiles")
    op.drop_index("ix_sourced_profiles_job_id", table_name="sourced_profiles")
    op.drop_table("sourced_profiles")
    op.drop_column("jobs", "sourcing")
