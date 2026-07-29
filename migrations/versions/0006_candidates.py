"""candidates table + applications.candidate_id (A3 dedup)

Revision ID: 0006_candidates
Revises: 0005_message_log
Create Date: 2026-07-25

A3 deduplicates incoming CVs against a candidate identity keyed by salted
email/phone hashes; an application links to its candidate via candidate_id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_candidates"
down_revision = "0005_message_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email_hash", sa.String(length=64), nullable=True),
        sa.Column("phone_hash", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_candidates_email_hash", "candidates", ["email_hash"])
    op.create_index("ix_candidates_phone_hash", "candidates", ["phone_hash"])
    op.add_column("applications", sa.Column("candidate_id", sa.Integer(), nullable=True))
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_candidate_id", table_name="applications")
    op.drop_column("applications", "candidate_id")
    op.drop_index("ix_candidates_phone_hash", table_name="candidates")
    op.drop_index("ix_candidates_email_hash", table_name="candidates")
    op.drop_table("candidates")
