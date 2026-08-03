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


# --- A2 kit caching + spec-aware prompt + sourced tracking -------------------


def test_sourcing_kit_is_cached_and_refreshable(client, auth_header, monkeypatch):
    """Reopening the panel must not burn another LLM call."""
    from app.routers import jobs as jobs_router

    calls: list[int] = []

    def fake(**_):
        calls.append(1)
        return _kit()

    monkeypatch.setattr(jobs_router, "generate_sourcing_kit", fake)
    job_id = _seed_job(client)

    client.post(f"/jobs/{job_id}/sourcing", headers=auth_header)
    client.post(f"/jobs/{job_id}/sourcing", headers=auth_header)  # served from cache
    assert len(calls) == 1

    # explicit refresh regenerates
    client.post(f"/jobs/{job_id}/sourcing?refresh=true", headers=auth_header)
    assert len(calls) == 2


def test_sourcing_uses_job_spec_for_precision(monkeypatch):
    """A1's must-haves must reach the sourcer prompt."""
    captured: dict = {}

    def fake(*, profile, messages, schema, **_):
        captured["content"] = messages[1]["content"]
        return _kit()

    monkeypatch.setattr(sourcer_mod, "llm_call", fake)
    generate_sourcing_kit(
        title="Backend Engineer",
        description="Build APIs",
        spec={"spec": {"seniority": "senior", "must_have": ["Python", "PostgreSQL"],
                       "eliminatory_criteria": ["5+ years"]}},
    )
    assert "MUST HAVE: Python, PostgreSQL" in captured["content"]
    assert "SENIORITY: senior" in captured["content"]
    assert "HARD REQUIREMENTS: 5+ years" in captured["content"]


def test_sourced_profile_tracking_and_duplicate_guard(client, auth_header):
    job_id = _seed_job(client)

    created = client.post(
        f"/jobs/{job_id}/sourced", headers=auth_header,
        json={"full_name": "Jane Doe", "profile_url": "https://linkedin.com/in/jane/"},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["status"] == "sourced"

    # same person again (trailing slash normalised) -> refused, no double contact
    dup = client.post(
        f"/jobs/{job_id}/sourced", headers=auth_header,
        json={"full_name": "Jane D", "profile_url": "https://linkedin.com/in/jane"},
    )
    assert dup.status_code == 409

    # mark contacted -> timestamp recorded
    upd = client.patch(
        f"/jobs/sourced/{sid}", headers=auth_header,
        json={"status": "contacted", "outreach_tone": "warm"},
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "contacted"
    assert upd.json()["contacted_at"] is not None

    listed = client.get(f"/jobs/{job_id}/sourced", headers=auth_header).json()
    assert len(listed) == 1 and listed[0]["outreach_tone"] == "warm"


def test_import_profile_marks_sourced_imported(client, auth_header, monkeypatch):
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "enqueue_application_step", lambda *a, **k: None)
    job_id = _seed_job(client)
    sid = client.post(
        f"/jobs/{job_id}/sourced", headers=auth_header,
        json={"full_name": "Sam", "profile_url": "https://linkedin.com/in/sam"},
    ).json()["id"]

    resp = client.post(
        f"/jobs/{job_id}/import-profile", headers=auth_header,
        json={"raw_text": "Sam — Python engineer", "full_name": "Sam", "sourced_id": sid},
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]

    listed = client.get(f"/jobs/{job_id}/sourced", headers=auth_header).json()
    assert listed[0]["status"] == "imported"
    assert listed[0]["application_id"] == app_id


# --- A2 file/CSV import + per-candidate outreach -----------------------------


def test_import_profile_upload_creates_application(client, auth_header, monkeypatch):
    """Spec §A2: uploaded profile exports flow through parsing + scoring."""
    from app.models.application import Application
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "enqueue_application_step", lambda *a, **k: None)
    job_id = _seed_job(client)

    resp = client.post(
        f"/jobs/{job_id}/import-profile/upload", headers=auth_header,
        data={"full_name": "Jane Doe"},
        files={"file": ("jane-profile.txt", b"Jane Doe\nSenior Backend Engineer\nPython, Go", "text/plain")},
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]

    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        row = db.get(Application, app_id)
        assert row.payload["source"] == "linkedin_assist"  # tagged like the paste path
        assert "Senior Backend Engineer" in row.payload["cv_text"]
    finally:
        db.close()


def test_import_profile_upload_rejects_bad_type(client, auth_header):
    job_id = _seed_job(client)
    resp = client.post(
        f"/jobs/{job_id}/import-profile/upload", headers=auth_header,
        files={"file": ("x.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_import_sourced_csv_bulk_and_dedupes(client, auth_header):
    job_id = _seed_job(client)
    csv_bytes = (
        b"name,profile_url,notes\n"
        b"Jane Doe,https://linkedin.com/in/jane/,strong python\n"
        b"Sam Lee,https://linkedin.com/in/sam,\n"
        b"Dup Person,https://linkedin.com/in/jane,should be skipped\n"
    )
    resp = client.post(
        f"/jobs/{job_id}/sourced/import-csv", headers=auth_header,
        files={"file": ("list.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 2 and body["skipped_duplicates"] == 1

    listed = client.get(f"/jobs/{job_id}/sourced", headers=auth_header).json()
    assert {p["full_name"] for p in listed} == {"Jane Doe", "Sam Lee"}

    # re-importing the same list adds nothing — all three rows are now known
    again = client.post(
        f"/jobs/{job_id}/sourced/import-csv", headers=auth_header,
        files={"file": ("list.csv", csv_bytes, "text/csv")},
    ).json()
    assert again["added"] == 0 and again["skipped_duplicates"] == 3


def test_personal_outreach_uses_profile(client, auth_header, monkeypatch):
    """Spec §A2: drafts personalised from JobSpec + what the recruiter pasted."""
    from app.agents.sourcer import OutreachDraft
    from app.routers import jobs as jobs_router

    captured: dict = {}

    def fake(*, title, profile_text, spec=None, user_id=None):
        captured.update(title=title, profile_text=profile_text)
        return [
            OutreachDraft(tone="warm", subject="s1", message="m1"),
            OutreachDraft(tone="direct", subject="s2", message="m2"),
            OutreachDraft(tone="casual", subject="s3", message="m3"),
        ]

    monkeypatch.setattr(jobs_router, "generate_personal_outreach", fake)
    job_id = _seed_job(client)

    resp = client.post(
        f"/jobs/{job_id}/outreach", headers=auth_header,
        json={"profile_text": "Led the payments migration at Acme"},
    )
    assert resp.status_code == 200
    assert [d["tone"] for d in resp.json()] == ["warm", "direct", "casual"]
    assert "payments migration" in captured["profile_text"]  # the profile reached the model


def test_personal_outreach_requires_a_profile(client, auth_header):
    job_id = _seed_job(client)
    resp = client.post(f"/jobs/{job_id}/outreach", headers=auth_header, json={})
    assert resp.status_code == 422
