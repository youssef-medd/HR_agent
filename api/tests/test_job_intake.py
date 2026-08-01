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


def test_jobintake_lifts_flattened_payload():
    """Models often emit spec fields at the top level of `intake` instead of
    nested under `spec`; those must not be silently dropped."""
    flat = JobIntake.model_validate(
        {
            "seniority": "Senior",
            "missions": ["Build the web app"],
            "must_have": ["Next.js", "TypeScript"],
            "eliminatory_criteria": ["5+ years"],
            "skills": 40,
            "experience": 30,
            "education": 10,
            "sector": 20,
            "linkedin_post": "We're hiring!",
        }
    )
    assert flat.spec.seniority == "Senior"
    assert flat.spec.must_have == ["Next.js", "TypeScript"]
    assert flat.spec.eliminatory_criteria == ["5+ years"]
    assert flat.weights.skills == 40 and flat.weights.sector == 20
    assert flat.channels.linkedin_post == "We're hiring!"


def test_jobintake_keeps_nested_payload():
    nested = JobIntake.model_validate(
        {"spec": {"seniority": "Mid", "must_have": ["Go"]}, "weights": {"skills": 50}}
    )
    assert nested.spec.seniority == "Mid" and nested.spec.must_have == ["Go"]
    assert nested.weights.skills == 50


def test_converse_forces_finalize_when_recruiter_defers(monkeypatch):
    """'you recommend to me' must stop the question loop (spec §A1 UX)."""
    from app.agents.job_intake import IntakeTurn, converse_intake

    captured: dict = {}

    def fake(**kw):
        captured["prompt"] = kw["messages"][1]["content"]
        return IntakeTurn(done=True, title="X", intake=_intake())

    monkeypatch.setattr(ji, "llm_call", fake)
    converse_intake("", [{"role": "user", "text": "you recommend to me"}])
    assert "must NOT ask another question" in captured["prompt"]


def test_converse_forces_finalize_after_question_limit(monkeypatch):
    from app.agents.job_intake import MAX_INTAKE_QUESTIONS, IntakeTurn, converse_intake

    captured: dict = {}

    def fake(**kw):
        captured["prompt"] = kw["messages"][1]["content"]
        return IntakeTurn(done=True, title="X", intake=_intake())

    monkeypatch.setattr(ji, "llm_call", fake)
    convo = []
    for _ in range(MAX_INTAKE_QUESTIONS):
        convo.append({"role": "assistant", "text": "q?"})
        convo.append({"role": "user", "text": "a"})
    converse_intake("", convo)
    assert "must NOT ask another question" in captured["prompt"]


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


def test_structure_sets_tracking_link(client, auth_header, monkeypatch):
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "structure_job", lambda **_: _intake())
    job_id = _seed_job(client)
    body = client.post(f"/jobs/{job_id}/structure", headers=auth_header).json()
    assert body["tracking_link"].endswith(f"/apply/{job_id}?src=careers")


def test_structure_from_brief_and_answers(client, auth_header, monkeypatch):
    from app.routers import jobs as jobs_router

    captured: dict = {}

    def fake(**kw):
        captured["raw"] = kw.get("raw_jd")
        return _intake()

    monkeypatch.setattr(jobs_router, "structure_job", fake)
    job_id = _seed_job(client)

    # free-text brief
    client.post(f"/jobs/{job_id}/structure", headers=auth_header, json={"brief": "Senior Go role, k8s"})
    assert "k8s" in captured["raw"]

    # six guided answers -> composed brief
    client.post(
        f"/jobs/{job_id}/structure", headers=auth_header,
        json={"answers": {"seniority": "senior", "must_have": "Go, Kubernetes"}},
    )
    assert "Go, Kubernetes" in captured["raw"] and "Seniority: senior" in captured["raw"]


def test_structure_upload(client, auth_header, monkeypatch):
    from app.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "structure_job", lambda **_: _intake())
    job_id = _seed_job(client)
    resp = client.post(
        f"/jobs/{job_id}/structure/upload", headers=auth_header,
        files={"file": ("jd.txt", b"Senior backend engineer, Python + Postgres", "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["spec"]["must_have"] == ["Python", "LLM"]


def test_structure_upload_rejects_bad_ext(client, auth_header):
    job_id = _seed_job(client)
    resp = client.post(
        f"/jobs/{job_id}/structure/upload", headers=auth_header,
        files={"file": ("jd.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_spec_override_saved(client, auth_header):
    job_id = _seed_job(client)
    intake = _intake().model_dump()
    intake["weights"]["skills"] = 40
    intake["channels"]["linkedin_post"] = "Edited by recruiter"

    resp = client.patch(f"/jobs/{job_id}/spec", headers=auth_header, json=intake)
    assert resp.status_code == 200
    body = resp.json()
    assert body["overridden"] is True
    assert body["weights"]["skills"] == 40

    from app.db import get_db
    from app.models.job import Job

    db = next(client.app.dependency_overrides[get_db]())
    try:
        spec = db.get(Job, job_id).spec
        assert spec["overridden"] is True
        assert spec["channels"]["linkedin_post"] == "Edited by recruiter"
    finally:
        db.close()


def test_intake_questions_endpoint(client, auth_header):
    resp = client.get("/jobs/intake/questions", headers=auth_header)
    assert resp.status_code == 200
    assert len(resp.json()) == 6
    assert {q["key"] for q in resp.json()} >= {"seniority", "must_have", "dealbreakers"}


def test_converse_intake_asks_then_finalizes(monkeypatch):
    from app.agents.job_intake import IntakeTurn, converse_intake

    # First turn: not enough info -> asks a question.
    monkeypatch.setattr(ji, "llm_call", lambda **_: IntakeTurn(done=False, question="Which cloud?"))
    t1 = converse_intake("ML Engineer", [{"role": "user", "text": "I want an ML engineer"}])
    assert t1.done is False and "cloud" in t1.question.lower() and t1.intake is None

    # Later turn: enough info -> finalizes.
    monkeypatch.setattr(ji, "llm_call", lambda **_: IntakeTurn(done=True, intake=_intake()))
    t2 = converse_intake("ML Engineer", [{"role": "user", "text": "AWS, PyTorch, 3y"}])
    assert t2.done is True and t2.intake is not None
    assert t2.intake.spec.must_have == ["Python", "LLM"]


def test_chat_intake_new_no_job(client, auth_header, monkeypatch):
    from app.agents.job_intake import IntakeTurn
    from app.routers import jobs as jobs_router

    # from-scratch converse: no job needed, nothing saved
    monkeypatch.setattr(jobs_router, "converse_intake",
                        lambda *a, **k: IntakeTurn(done=False, question="What seniority?"))
    resp = client.post("/jobs/intake/converse", headers=auth_header,
                       json={"messages": [{"role": "user", "text": "I want an ML engineer"}]})
    assert resp.status_code == 200
    assert resp.json()["done"] is False and resp.json()["question"] == "What seniority?"


def test_intake_extract_reads_text_file(client, auth_header):
    """A1 — the AI chat can attach a JD before any job exists."""
    resp = client.post(
        "/jobs/intake/extract", headers=auth_header,
        files={"file": ("jd.txt", b"Senior Frontend Engineer\nNext.js, React", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "jd.txt"
    assert "Next.js" in body["text"]
    assert body["chars"] == len(body["text"])


def test_intake_extract_rejects_bad_extension(client, auth_header):
    resp = client.post(
        "/jobs/intake/extract", headers=auth_header,
        files={"file": ("jd.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_intake_extract_rejects_empty_text(client, auth_header):
    resp = client.post(
        "/jobs/intake/extract", headers=auth_header,
        files={"file": ("jd.txt", b"   \n  ", "text/plain")},
    )
    assert resp.status_code == 422


def test_intake_extract_requires_auth(client):
    resp = client.post(
        "/jobs/intake/extract",
        files={"file": ("jd.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 401


def test_chat_intake_create_makes_job(client, auth_header):
    intake = _intake().model_dump()
    resp = client.post("/jobs/intake/create", headers=auth_header,
                       json={"title": "ML Engineer", "intake": intake})
    assert resp.status_code == 200
    body = resp.json()
    job_id = body["job_id"]
    assert body["intake"]["tracking_link"].endswith(f"/apply/{job_id}?src=careers")

    # the job now exists, published, with the spec persisted
    from app.db import get_db
    from app.models.job import Job

    db = next(client.app.dependency_overrides[get_db]())
    try:
        job = db.get(Job, job_id)
        assert job is not None and job.title == "ML Engineer" and job.status == "published"
        assert job.spec["spec"]["seniority"] == "senior"
        assert "Required:" in job.description
    finally:
        db.close()


def test_converse_endpoint_question_then_save(client, auth_header, monkeypatch):
    from app.agents.job_intake import IntakeTurn
    from app.routers import jobs as jobs_router

    job_id = _seed_job(client)

    # Not done -> returns the question, nothing persisted.
    monkeypatch.setattr(jobs_router, "converse_intake",
                        lambda *a, **k: IntakeTurn(done=False, question="Seniority?"))
    r1 = client.post(f"/jobs/{job_id}/intake/converse", headers=auth_header,
                     json={"messages": [{"role": "user", "text": "ML engineer"}]})
    assert r1.status_code == 200 and r1.json()["done"] is False
    assert r1.json()["question"] == "Seniority?"

    # Done -> persists spec + adds tracking link.
    monkeypatch.setattr(jobs_router, "converse_intake",
                        lambda *a, **k: IntakeTurn(done=True, intake=_intake()))
    r2 = client.post(f"/jobs/{job_id}/intake/converse", headers=auth_header,
                     json={"messages": [{"role": "user", "text": "senior, AWS"}]})
    body = r2.json()
    assert body["done"] is True
    assert body["intake"]["tracking_link"].endswith(f"/apply/{job_id}?src=careers")

    from app.db import get_db
    from app.models.job import Job

    db = next(client.app.dependency_overrides[get_db]())
    try:
        assert db.get(Job, job_id).spec["spec"]["seniority"] == "senior"
    finally:
        db.close()
