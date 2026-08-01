"""A1 — ESCO skill-taxonomy normalization."""

from __future__ import annotations

from app.agents.taxonomy import normalize_skill, normalize_skills
from app.models.esco_skill import EscoSkill


def _seed(client):
    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        db.add_all([
            EscoSkill(label="Python", normalized="python"),
            EscoSkill(label="PostgreSQL", normalized="postgresql"),
            EscoSkill(label="Kubernetes", normalized="kubernetes"),
        ])
        db.commit()
    finally:
        db.close()


def test_normalize_skill_exact_fuzzy_passthrough():
    tax = [("python", "Python"), ("postgresql", "PostgreSQL"), ("kubernetes", "Kubernetes")]
    assert normalize_skill("python", tax) == "Python"        # exact, case-insensitive
    assert normalize_skill("Postgres", tax) == "Postgres"    # below fuzzy floor -> kept
    assert normalize_skill("kubernets", tax) == "Kubernetes" # typo -> fuzzy match
    assert normalize_skill("Cobol", tax) == "Cobol"          # no match -> verbatim


def test_normalize_skills_dedupes(client):
    _seed(client)
    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        out = normalize_skills(db, ["python", "Python", "k8s stuff", "Kubernetes"])
        assert "Python" in out and out.count("Python") == 1  # de-duplicated
        assert "Kubernetes" in out
    finally:
        db.close()


def test_normalize_skills_empty_taxonomy_passthrough(client):
    # No seeded taxonomy -> skills returned unchanged.
    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        assert normalize_skills(db, ["Foo", "Bar"]) == ["Foo", "Bar"]
    finally:
        db.close()
