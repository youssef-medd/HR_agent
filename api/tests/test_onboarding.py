"""A8 onboarding — agent generation + the /applications/{id}/onboarding endpoint."""

from __future__ import annotations

import pytest

from app.agents import onboarder as onboarder_mod
from app.agents.onboarder import (
    OnboardingError,
    OnboardingKit,
    OnboardingTask,
    generate_onboarding_kit,
)
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def _kit() -> OnboardingKit:
    return OnboardingKit(
        welcome_message="Welcome [first name]!",
        checklist=["Create email", "Order laptop"],
        week_one_plan=[OnboardingTask(when="Day 1", task="Meet the team")],
        documents=["Employment contract"],
    )


def test_generate_onboarding_kit_uses_chat_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return _kit()

    monkeypatch.setattr(onboarder_mod, "llm_call", fake_llm_call)

    kit = generate_onboarding_kit(role_title="Backend Engineer", candidate_name="Jane", user_id="1")

    assert isinstance(kit, OnboardingKit)
    assert kit.checklist and kit.week_one_plan[0].when == "Day 1"
    assert captured["profile"] == "chat"
    assert captured["schema"] is OnboardingKit
    assert captured["metadata"]["agent"] == "A8"


def test_generate_wraps_validation_error(monkeypatch):
    def boom(**_):
        return OnboardingKit.model_validate({"checklist": "not-a-list"})

    monkeypatch.setattr(onboarder_mod, "llm_call", boom)
    with pytest.raises(OnboardingError):
        generate_onboarding_kit(role_title="X")


def _seed_app(client) -> int:
    from app.db import get_db
    from app.models.application import Application
    from app.models.job import Job

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        db.add(Job(id=1, title="Backend Engineer", department="Engineering", status="published"))
        row = Application(
            job_id=1, candidate_ref="jane@x.io", state="HIRED",
            payload={"cv": {"full_name": "Jane Doe"}},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_onboarding_endpoint_requires_auth(client):
    assert client.post("/applications/1/onboarding").status_code == 401


def test_onboarding_endpoint_returns_kit(client, auth_header, monkeypatch):
    from app.routers import applications as apps_router

    seen: dict = {}

    def fake_generate(**kwargs):
        seen.update(kwargs)
        return _kit()

    monkeypatch.setattr(apps_router, "generate_onboarding_kit", fake_generate)

    app_id = _seed_app(client)
    resp = client.post(f"/applications/{app_id}/onboarding", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["checklist"] == ["Create email", "Order laptop"]
    assert body["week_one_plan"][0]["when"] == "Day 1"
    # role + candidate resolved from the job and parsed CV
    assert seen["role_title"] == "Backend Engineer"
    assert seen["candidate_name"] == "Jane Doe"


def test_onboarding_endpoint_404_for_missing_app(client, auth_header):
    assert client.post("/applications/9999/onboarding", headers=auth_header).status_code == 404
