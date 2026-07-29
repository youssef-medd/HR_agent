"""pgvector application_embeddings (A4 semantic pre-ranking)

Revision ID: 0007_embeddings
Revises: 0006_candidates
Create Date: 2026-07-25

Enables the pgvector extension and stores one profile embedding per application
for cosine pre-ranking (spec §A4 stage 2). Dimension = EMBED_DIM (bge-m3 = 1024).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_embeddings"
down_revision = "0006_candidates"
branch_labels = None
depends_on = None

_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS application_embeddings (
            application_id INTEGER PRIMARY KEY
                REFERENCES applications(id) ON DELETE CASCADE,
            embedding vector({_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.drop_table("application_embeddings")
    # Leave the extension installed — other objects may use it.
