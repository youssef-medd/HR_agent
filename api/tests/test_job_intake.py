"""A1 job-intake — structuring a raw JD into JobSpec + weights + channels."""

from __future__ import annotations

import pytest

from app.agents import job_intake as ji
from app.agents.job_intake import (
    ChannelContent,
    JobIntake,
    JobIntakeError,
    JobSpec,
    Weights,
    structure_job,
)
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def _intake() -> JobIntake:
    return JobIntake(
        spec=JobSpec(
            seniority="senior",
            location="Tunis",
            missions=["Build AI features"],
            must_have=["Python", "LLM"],
            nice_to_have=["Next.js"],
            languages=["English", "French"],
            eliminatory_criteria=["Fluent English required"],
        ),
        weights=Weights(skills=55, experience=30, education=15),
        channels=ChannelContent(
            linkedin_post="We're hiring! #AI",
            job_board_text="AI Engineer wanted.",
            careers_page="Join us.",
            whatsapp_blurb="AI Engineer role open.",
        ),
    )


def test_structure_job_uses_judge_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return _intake()

    monkeypatch.setattr(ji, "llm_call", fake_llm_call)

    out = structure_job(title="AI Engineer", raw_jd="Build the AI layer...", user_id="1")

    assert isinstance(out, JobIntake)
    assert out.spec.must_have == ["Python", "LLM"]
    assert out.spec.eliminatory_criteria == ["Fluent English required"]
    assert out.weights.skills == 55
    assert captured["profile"] == "judge"
    assert captured["schema"] is JobIntake
    assert captured["metadata"]["agent"] == "A1"


def test_structure_job_wraps_validation_error(monkeypatch):
    def boom(**_):
        return JobIntake.model_validate({"weights": {"skills": 999}})  # ge/le violated

    monkeypatch.setattr(ji, "llm_call", boom)
    with pytest.raises(JobIntakeError):
        structure_job(title="X", raw_jd="y")


def _seed_job(client) -> int:
    from app.db import get_db
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        job = Job(title="AI Engineer", description="Build AI. Must have Python and LLM.", status="published")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def test_structure_endpoint_stores_spec(client, auth_header, monkeypatch):
    from app.models.job import Job
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "structure_job", lambda **_: _intake())
    job_id = _seed_job(client)

    resp = client.post(f"/jobs/{job_id}/structure", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["spec"]["must_have"] == ["Python", "LLM"]
    assert body["weights"]["skills"] == 55

    # persisted on the job + surfaced in the job view
    from app.db import get_db

    db = next(client.app.dependency_overrides[get_db]())
    try:
        assert db.get(Job, job_id).spec["spec"]["seniority"] == "senior"
    finally:
        db.close()

    view = client.get(f"/jobs/{job_id}", headers=auth_header).json()
    assert view["spec"]["weights"]["experience"] == 30


def test_structure_endpoint_404(client, auth_header):
    assert client.post("/jobs/99999/structure", headers=auth_header).status_code == 404
