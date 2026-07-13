"""Jobs endpoints + JD-inheritance-at-intake tests."""

from __future__ import annotations

import pytest

from app.routers import applications as app_router
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch):
    monkeypatch.setattr(app_router, "enqueue_application_step", lambda *a, **k: None)


def test_create_job_requires_auth(client):
    assert client.post("/jobs", json={"title": "AI Engineer"}).status_code == 401


def test_create_and_list_job(client, auth_header):
    resp = client.post(
        "/jobs",
        json={
            "title": "AI Engineer",
            "department": "Engineering",
            "location": "Tunis",
            "description": "Python, RAG, LangGraph required.",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["title"] == "AI Engineer"
    assert job["status"] == "published"

    rows = client.get("/jobs", headers=auth_header).json()
    assert any(r["id"] == job["id"] for r in rows)

    one = client.get(f"/jobs/{job['id']}", headers=auth_header).json()
    assert one["description"].startswith("Python")


def test_get_missing_job_404(client, auth_header):
    assert client.get("/jobs/99999", headers=auth_header).status_code == 404


def test_upload_inherits_job_description(client, auth_header):
    job = client.post(
        "/jobs",
        json={"title": "Backend Engineer", "description": "FastAPI and PostgreSQL required."},
        headers=auth_header,
    ).json()

    resp = client.post(
        "/applications",
        data={"job_id": str(job["id"]), "candidate_ref": "inherit@example.com"},
        files={"file": ("cv.txt", b"Jane Doe, Python dev", "text/plain")},
        headers=auth_header,
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]

    # jd_text inherited from the job's description
    from app.db import get_db
    from app.models.application import Application

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row = db.get(Application, app_id)
        assert row.payload["jd_text"] == "FastAPI and PostgreSQL required."
    finally:
        db.close()


def test_upload_explicit_jd_overrides_job(client, auth_header):
    job = client.post(
        "/jobs",
        json={"title": "Some Job", "description": "job text"},
        headers=auth_header,
    ).json()

    resp = client.post(
        "/applications",
        data={
            "job_id": str(job["id"]),
            "candidate_ref": "override@example.com",
            "job_description": "explicit text",
        },
        files={"file": ("cv.txt", b"Jane", "text/plain")},
        headers=auth_header,
    )
    app_id = resp.json()["application_id"]

    from app.db import get_db
    from app.models.application import Application

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        assert db.get(Application, app_id).payload["jd_text"] == "explicit text"
    finally:
        db.close()
