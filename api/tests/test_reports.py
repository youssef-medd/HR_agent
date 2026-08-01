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

    assert len(body["per_job"]) == 1
    pj = body["per_job"][0]
    assert pj["job_id"] == 1 and pj["applicants"] == 3 and pj["shortlisted"] == 1
    assert pj["avg_score"] == 65.0  # (80 + 50) / 2
    assert pj["score_buckets"] == {"70-84": 1, "45-69": 1}  # scores 80 and 50

    # Source conversion (both seeded apps have no source -> "upload").
    assert body["source_conversion"]["upload"]["applied"] == 3
    assert body["source_conversion"]["upload"]["shortlisted"] == 1
    # Overall score distribution
    assert body["score_distribution"]["70-84"] == 1 and body["score_distribution"]["45-69"] == 1


def test_overview_empty(client, auth_header):
    resp = client.get("/reports/overview", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_applications"] == 0
    assert body["avg_score"] is None
    assert body["shortlist_rate"] == 0.0
    assert {f["stage"] for f in body["funnel"]} >= {"RECEIVED", "HIRED"}


def test_applications_csv_export(client, auth_header):
    _seed(client)
    resp = client.get("/reports/applications.csv", headers=auth_header)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=applications.csv" in resp.headers["content-disposition"]

    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("id,job_id,job_title,candidate_ref,state,source")
    assert len(lines) == 4  # header + 3 apps
    assert any("a@x.io" in row and ",80," in row for row in lines[1:])


def test_applications_csv_requires_auth(client):
    assert client.get("/reports/applications.csv").status_code == 401


def test_message_center_lists_recent(client, auth_header):
    from app.db import get_db
    from app.models.message_log import MessageLog

    db = next(client.app.dependency_overrides[get_db]())
    try:
        db.add_all([
            MessageLog(application_id=1, recipient="a@x.io", channel="email",
                       template_id="offer", rendered_body="Your offer, Sara", status="sent"),
            MessageLog(application_id=1, recipient="+216", channel="whatsapp",
                       template_id="prescreen_question", rendered_body="Q1?", status="stub"),
        ])
        db.commit()
    finally:
        db.close()

    resp = client.get("/reports/messages", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {r["channel"] for r in body} == {"email", "whatsapp"}
    assert any(r["body"] == "Your offer, Sara" for r in body)


def test_message_center_requires_recruiter(client):
    assert client.get("/reports/messages").status_code == 401


def test_messaging_summary(client, auth_header):
    from app.db import get_db
    from app.models.message_log import MessageLog

    db = next(client.app.dependency_overrides[get_db]())
    try:
        db.add_all([
            MessageLog(recipient="a@x.io", channel="email", template_id="offer",
                       rendered_body="x", status="sent"),
            MessageLog(recipient="a@x.io", channel="email", template_id="offer",
                       rendered_body="x", status="skipped_rate_limited"),
            MessageLog(recipient="+216", channel="whatsapp", template_id="prescreen_question",
                       rendered_body="x", status="stub"),
        ])
        db.commit()
    finally:
        db.close()

    resp = client.get("/reports/messaging", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["by_channel"] == {"email": 2, "whatsapp": 1}
    assert body["rate_limited"] == 1
    assert body["by_template"]["offer"] == 2
