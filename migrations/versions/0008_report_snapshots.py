"""report_snapshots table (A9 nightly aggregate)

Revision ID: 0008_report_snapshots
Revises: 0007_embeddings
Create Date: 2026-07-30

A9 nightly aggregation job stores a KPI snapshot per run for trend charts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_report_snapshots"
down_revision = "0007_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "taken_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default="{}"),
    )
    op.create_index("ix_report_snapshots_taken_at", "report_snapshots", ["taken_at"])


def downgrade() -> None:
    op.drop_index("ix_report_snapshots_taken_at", table_name="report_snapshots")
    op.drop_table("report_snapshots")
