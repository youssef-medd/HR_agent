"""esco_skills taxonomy (A1)

Revision ID: 0010_esco_skills
Revises: 0009_onboarding_tasks
Create Date: 2026-07-30

A small seeded canonical skill taxonomy A1 normalises extracted skills against.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_esco_skills"
down_revision = "0009_onboarding_tasks"
branch_labels = None
depends_on = None

# Starter taxonomy — canonical labels. Extend by loading the real ESCO dump.
_SEED = [
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "Ruby", "PHP",
    "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Docker", "Kubernetes", "Terraform", "Ansible", "Linux",
    "AWS", "Google Cloud Platform", "Microsoft Azure",
    "React", "Next.js", "Vue.js", "Angular", "Node.js", "FastAPI", "Django", "Flask", "Spring",
    "Machine Learning", "Deep Learning", "Natural Language Processing", "Computer Vision",
    "TensorFlow", "PyTorch", "Data Analysis", "Data Engineering",
    "CI/CD", "Git", "REST APIs", "GraphQL", "Microservices", "Kafka", "RabbitMQ",
    "Agile", "Scrum", "Test-Driven Development", "Project Management",
    "English", "French", "Arabic", "German", "Spanish",
]


def upgrade() -> None:
    op.create_table(
        "esco_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(length=128), nullable=False, unique=True),
        sa.Column("normalized", sa.String(length=128), nullable=False),
    )
    op.create_index("ix_esco_skills_normalized", "esco_skills", ["normalized"])
    op.bulk_insert(
        sa.table(
            "esco_skills",
            sa.column("label", sa.String),
            sa.column("normalized", sa.String),
        ),
        [{"label": s, "normalized": s.lower()} for s in _SEED],
    )


def downgrade() -> None:
    op.drop_index("ix_esco_skills_normalized", table_name="esco_skills")
    op.drop_table("esco_skills")
