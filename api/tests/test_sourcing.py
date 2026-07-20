"""A2 sourcing — agent generation + the /jobs/{id}/sourcing endpoint."""

from __future__ import annotations

import pytest

from app.agents import sourcer as sourcer_mod
from app.agents.sourcer import SourcingError, SourcingKit, generate_sourcing_kit
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def test_generate_sourcing_kit_uses_chat_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return SourcingKit(
            boolean_search='("Backend Engineer" OR "Software Engineer") AND (Python OR Go)',
            keywords=["Python", "Go", "PostgreSQL"],
            platforms=["LinkedIn", "GitHub"],
            outreach_subject="Backend role at [company]",
            outreach_message="Hi [first name], ...",
        )

    monkeypatch.setattr(sourcer_mod, "llm_call", fake_llm_call)

    kit = generate_sourcing_kit(title="Backend Engineer", description="Python, Go", user_id="1")

    assert isinstance(kit, SourcingKit)
    assert "Python" in kit.keywords
    assert kit.boolean_search.startswith("(")
    assert captured["profile"] == "chat"
    assert captured["schema"] is SourcingKit
    assert captured["metadata"]["agent"] == "A2"


def test_generate_wraps_validation_error(monkeypatch):
    def boom(**_):
        return SourcingKit.model_validate({"keywords": "not-a-list"})

    monkeypatch.setattr(sourcer_mod, "llm_call", boom)
    with pytest.raises(SourcingError):
        generate_sourcing_kit(title="X")


def _seed_job(client) -> int:
    from app.db import get_db
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        job = Job(title="Backend Engineer", description="Python, Go", status="published")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def test_sourcing_endpoint_requires_auth(client):
    assert client.post("/jobs/1/sourcing").status_code == 401


def test_sourcing_endpoint_returns_kit(client, auth_header, monkeypatch):
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(
        jobs_router,
        "generate_sourcing_kit",
        lambda **_: SourcingKit(
            boolean_search="(Python OR Go)",
            keywords=["Python"],
            platforms=["LinkedIn"],
            outreach_subject="Hi",
            outreach_message="Hello [first name]",
        ),
    )

    job_id = _seed_job(client)
    resp = client.post(f"/jobs/{job_id}/sourcing", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["keywords"] == ["Python"]
    assert body["boolean_search"] == "(Python OR Go)"


def test_sourcing_endpoint_404_for_missing_job(client, auth_header):
    assert client.post("/jobs/9999/sourcing", headers=auth_header).status_code == 404
