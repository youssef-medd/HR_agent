"""A2 sourcing — kit generation, sourcing endpoint, and profile import."""

from __future__ import annotations

import pytest

from app.agents import sourcer as sourcer_mod
from app.agents.sourcer import (
    OutreachDraft,
    SourcingError,
    SourcingKit,
    generate_sourcing_kit,
)
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def _kit() -> SourcingKit:
    return SourcingKit(
        search_strings=[
            'site:linkedin.com/in ("Backend Engineer") (Python OR Go)',
            '("Software Engineer") AND Python AND PostgreSQL',
        ],
        keywords=["Python", "Go", "PostgreSQL"],
        platforms=["LinkedIn", "GitHub"],
        outreach=[
            OutreachDraft(tone="warm", subject="Backend role", message="Hi [first name], ..."),
            OutreachDraft(tone="direct", subject="Backend @ [company]", message="[first name] — ..."),
            OutreachDraft(tone="casual", subject="quick one", message="hey [first name] ..."),
        ],
    )


def test_generate_sourcing_kit_uses_chat_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return _kit()

    monkeypatch.setattr(sourcer_mod, "llm_call", fake_llm_call)

    kit = generate_sourcing_kit(title="Backend Engineer", description="Python, Go", user_id="1")

    assert isinstance(kit, SourcingKit)
    assert len(kit.search_strings) == 2 and "Python" in kit.keywords
    assert [o.tone for o in kit.outreach] == ["warm", "direct", "casual"]
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

    monkeypatch.setattr(jobs_router, "generate_sourcing_kit", lambda **_: _kit())

    job_id = _seed_job(client)
    resp = client.post(f"/jobs/{job_id}/sourcing", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["keywords"] == ["Python", "Go", "PostgreSQL"]
    assert len(body["search_strings"]) == 2
    assert len(body["outreach"]) == 3


def test_sourcing_endpoint_404_for_missing_job(client, auth_header):
    assert client.post("/jobs/9999/sourcing", headers=auth_header).status_code == 404


def test_import_profile_creates_scored_application(client, auth_header, monkeypatch):
    from app.models.application import Application
    from app.routers import jobs as jobs_router

    enqueued: list = []
    monkeypatch.setattr(jobs_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    job_id = _seed_job(client)
    resp = client.post(
        f"/jobs/{job_id}/import-profile",
        json={
            "raw_text": "Backend engineer, 6 years Python, Go, PostgreSQL, Docker.",
            "full_name": "Sourced Person",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]
    assert enqueued == [(app_id,)]

    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        row = db.get(Application, app_id)
        assert row.state == "RECEIVED"
        assert row.payload["source"] == "linkedin_assist"
        assert row.payload["cv_text"].startswith("Backend engineer")
        assert row.candidate_ref == "Sourced Person"
    finally:
        db.close()


def test_import_profile_404_for_missing_job(client, auth_header):
    resp = client.post(
        "/jobs/9999/import-profile", json={"raw_text": "x"}, headers=auth_header
    )
    assert resp.status_code == 404
