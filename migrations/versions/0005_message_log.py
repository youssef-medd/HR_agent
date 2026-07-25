"""message_log table (A7)

Revision ID: 0005_message_log
Revises: 0004_job_spec
Create Date: 2026-07-25

A7 messaging integrity: every outbound candidate message (email/WhatsApp) is
recorded with its rendered body, template, channel and delivery status. This is
the audit surface and the table the per-candidate rate-limiter reads.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_message_log"
down_revision = "0004_job_spec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=True),
        sa.Column("rendered_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("validated_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_message_log_application_id", "message_log", ["application_id"])
    op.create_index("ix_message_log_recipient", "message_log", ["recipient"])
    op.create_index("ix_message_log_created_at", "message_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_message_log_created_at", table_name="message_log")
    op.drop_index("ix_message_log_recipient", table_name="message_log")
    op.drop_index("ix_message_log_application_id", table_name="message_log")
    op.drop_table("message_log")
