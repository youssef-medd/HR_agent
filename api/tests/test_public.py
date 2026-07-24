"""Public candidate endpoints — open-job listing and unauthenticated apply."""

from __future__ import annotations


def _seed_job(client, status: str = "published", description: str = "Backend role") -> int:
    from app.db import get_db
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        job = Job(title="Backend Engineer", status=status, description=description)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def test_list_open_jobs_only_published(client):
    published = _seed_job(client, "published")
    _seed_job(client, "draft")

    resp = client.get("/public/jobs")
    assert resp.status_code == 200
    ids = [j["id"] for j in resp.json()]
    assert published in ids
    assert len(ids) == 1  # draft excluded


def test_get_open_job_404_for_draft(client):
    draft = _seed_job(client, "draft")
    assert client.get(f"/public/jobs/{draft}").status_code == 404


def test_apply_creates_application_and_enqueues(client, monkeypatch):
    from app.models.application import Application
    from app.routers import public as public_router

    enqueued: list = []
    monkeypatch.setattr(public_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    job_id = _seed_job(client, "published", description="Backend role")

    resp = client.post(
        "/public/apply",
        data={
            "job_id": str(job_id),
            "email": "cand@x.io",
            "full_name": "Jane Doe",
            "phone": "+216 93 008 267",
        },
        files={"file": ("cv.txt", b"Python, SQL, 5 years", "text/plain")},
    )
    assert resp.status_code == 201
    app_id = resp.json()["application_id"]
    assert resp.json()["state"] == "RECEIVED"
    assert enqueued == [(app_id,)]

    from app.db import get_db

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row = db.get(Application, app_id)
        assert row.candidate_ref == "cand@x.io"
        assert row.payload["source"] == "web"
        assert row.payload["applicant_name"] == "Jane Doe"
        assert row.payload["phone"] == "+216 93 008 267"
        assert row.payload["jd_text"] == "Backend role"
        assert row.payload["cv_filename"] == "cv.txt"
    finally:
        db.close()


def test_apply_to_draft_job_404(client):
    draft = _seed_job(client, "draft")
    resp = client.post(
        "/public/apply",
        data={"job_id": str(draft), "email": "c@x.io"},
        files={"file": ("cv.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 404


def test_apply_rejects_bad_extension(client):
    job_id = _seed_job(client, "published")
    resp = client.post(
        "/public/apply",
        data={"job_id": str(job_id), "email": "c@x.io"},
        files={"file": ("cv.exe", b"data", "application/octet-stream")},
    )
    assert resp.status_code == 415


def _seed_tracked(client) -> int:
    from app.db import get_db
    from app.models.application import Application
    from app.models.application_event import ApplicationEvent
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        db.add(Job(id=1, title="Backend Engineer", status="published"))
        row = Application(job_id=1, candidate_ref="Jane@X.io", state="SCORED", payload={})
        db.add(row)
        db.commit()
        db.refresh(row)
        for to in ("PARSED", "SCORED"):
            db.add(ApplicationEvent(application_id=row.id, kind="transition", to_state=to, step=to.lower()))
        db.commit()
        return row.id
    finally:
        db.close()


def test_track_returns_status_and_timeline(client):
    app_id = _seed_tracked(client)
    # email match is case-insensitive
    resp = client.get("/public/track", params={"email": "jane@x.io", "application_id": app_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "SCORED"
    assert body["job_title"] == "Backend Engineer"
    assert [t["state"] for t in body["timeline"]] == ["PARSED", "SCORED"]


def test_track_wrong_email_404(client):
    app_id = _seed_tracked(client)
    resp = client.get("/public/track", params={"email": "someone@else.io", "application_id": app_id})
    assert resp.status_code == 404


def test_track_missing_application_404(client):
    resp = client.get("/public/track", params={"email": "jane@x.io", "application_id": 99999})
    assert resp.status_code == 404
