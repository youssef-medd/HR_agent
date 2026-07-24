"""A9 reporting endpoint — funnel reach/conversion, avg score, per-job."""

from __future__ import annotations

import pytest

from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def _seed(client):
    from app.db import get_db
    from app.models.application import Application
    from app.models.application_event import ApplicationEvent
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        db.add(Job(id=1, title="Backend", status="published", description="x"))

        # App 1: reached SHORTLISTED, scored 80.
        a1 = Application(job_id=1, candidate_ref="a@x.io", state="SHORTLISTED", payload={"score": {"overall": 80}})
        # App 2: reached SCORED only, scored 50.
        a2 = Application(job_id=1, candidate_ref="b@x.io", state="SCORED", payload={"score": {"overall": 50}})
        # App 3: still RECEIVED, no score.
        a3 = Application(job_id=1, candidate_ref="c@x.io", state="RECEIVED", payload={})
        db.add_all([a1, a2, a3])
        db.commit()
        for a in (a1, a2, a3):
            db.refresh(a)

        # Transition events: a1 PARSED, SCORED, SHORTLISTED; a2 PARSED, SCORED.
        for to in ("PARSED", "SCORED", "SHORTLISTED"):
            db.add(ApplicationEvent(application_id=a1.id, kind="transition", to_state=to, step=to.lower()))
        for to in ("PARSED", "SCORED"):
            db.add(ApplicationEvent(application_id=a2.id, kind="transition", to_state=to, step=to.lower()))
        db.commit()
    finally:
        db.close()


def test_overview_requires_auth(client):
    assert client.get("/reports/overview").status_code == 401


def test_overview_funnel_and_scores(client, auth_header):
    _seed(client)

    resp = client.get("/reports/overview", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_applications"] == 3
    assert body["by_state"]["SHORTLISTED"] == 1
    assert body["by_source"]["upload"] == 3  # seeded apps have no source tag

    funnel = {f["stage"]: f for f in body["funnel"]}
    assert funnel["RECEIVED"]["reached"] == 3
    assert funnel["PARSED"]["reached"] == 2
    assert funnel["SCORED"]["reached"] == 2
    assert funnel["SHORTLISTED"]["reached"] == 1
    assert funnel["HIRED"]["reached"] == 0

    # SCORED reached 2 of 2 parsed -> rate 1.0; SHORTLISTED 1 of 2 -> 0.5
    assert funnel["SCORED"]["rate_from_prev"] == 1.0
    assert funnel["SHORTLISTED"]["rate_from_prev"] == 0.5

    # avg score over the two scored apps: (80 + 50) / 2
    assert body["avg_score"] == 65.0
    assert body["shortlist_rate"] == round(1 / 3, 4)
    assert body["hire_rate"] == 0.0

    assert body["per_job"] == [
        {"job_id": 1, "title": "Backend", "applicants": 3, "shortlisted": 1}
    ]


def test_overview_empty(client, auth_header):
    resp = client.get("/reports/overview", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_applications"] == 0
    assert body["avg_score"] is None
    assert body["shortlist_rate"] == 0.0
    assert {f["stage"] for f in body["funnel"]} >= {"RECEIVED", "HIRED"}
