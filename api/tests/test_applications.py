"""Upload endpoint tests — offline (the Celery enqueue is monkeypatched).

The orchestrator run itself is exercised in the worker suite; here we only
assert the HTTP intake: auth, validation, row creation, and that a step is
enqueued exactly once.
"""

from __future__ import annotations

import pytest

from app import queue
from app.routers import applications as app_router
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(app_router, "enqueue_application_step", lambda *a, **k: calls.append((a, k)))
    return calls


def test_upload_requires_auth(client):
    resp = client.post("/applications", data={"job_id": "1"}, files={"file": ("cv.txt", b"hi")})
    assert resp.status_code == 401


def test_upload_creates_application_and_enqueues(client, auth_header, _stub_enqueue):
    resp = client.post(
        "/applications",
        data={"job_id": "1", "candidate_ref": "jane@example.com"},
        files={"file": ("cv.txt", b"Jane Doe, Python developer", "text/plain")},
        headers=auth_header,
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]
    assert resp.json()["state"] == "RECEIVED"
    assert len(_stub_enqueue) == 1
    assert _stub_enqueue[0][0][0] == app_id

    view = client.get(f"/applications/{app_id}", headers=auth_header)
    assert view.status_code == 200
    assert view.json()["candidate_ref"] == "jane@example.com"
    assert view.json()["cv"] is None  # not parsed yet (worker not run in unit test)


def test_upload_rejects_unsupported_extension(client, auth_header):
    resp = client.post(
        "/applications",
        data={"job_id": "1"},
        files={"file": ("cv.rtf", b"whatever", "application/rtf")},
        headers=auth_header,
    )
    assert resp.status_code == 415


def test_upload_rejects_empty_file(client, auth_header):
    resp = client.post(
        "/applications",
        data={"job_id": "1"},
        files={"file": ("cv.txt", b"", "text/plain")},
        headers=auth_header,
    )
    assert resp.status_code == 400


def test_get_missing_application_404(client, auth_header):
    assert client.get("/applications/99999", headers=auth_header).status_code == 404


def test_list_applications_returns_uploaded(client, auth_header, _stub_enqueue):
    client.post(
        "/applications",
        data={"job_id": "2", "candidate_ref": "list-me@example.com"},
        files={"file": ("cv.txt", b"Jane Doe", "text/plain")},
        headers=auth_header,
    )
    resp = client.get("/applications", headers=auth_header)
    assert resp.status_code == 200
    rows = resp.json()
    row = next(r for r in rows if r["candidate_ref"] == "list-me@example.com")
    assert row["state"] == "RECEIVED"
    assert row["score"] is None  # not scored yet


def test_upload_accepts_job_description(client, auth_header, _stub_enqueue):
    resp = client.post(
        "/applications",
        data={"job_id": "3", "candidate_ref": "jd@example.com", "job_description": "Senior Python role"},
        files={"file": ("cv.txt", b"Jane Doe", "text/plain")},
        headers=auth_header,
    )
    assert resp.status_code == 201


def test_enqueue_targets_named_task():
    assert queue.RUN_APPLICATION_STEP == "orchestrator.run_application_step"
