"""Needs-attention list endpoint tests."""

from __future__ import annotations

import pytest

from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


def test_needs_attention_requires_auth(client):
    assert client.get("/needs-attention").status_code == 401


def test_needs_attention_lists_open_gate_with_candidate_name(client, auth_header):
    from app.db import Base, get_db
    from app.models.application import Application
    from app.models.needs_attention import NeedsAttention

    # reuse the app's overridden test session
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        app_row = Application(
            job_id=1,
            candidate_ref="cand@example.com",
            state="DECLINE_PENDING",
            payload={"cv": {"full_name": "Jane Doe"}},
        )
        db.add(app_row)
        db.commit()
        db.refresh(app_row)
        db.add(
            NeedsAttention(
                application_id=app_row.id,
                reason="sensitive_gate",
                gate="rejection",
                status="open",
                context={},
            )
        )
        db.commit()
    finally:
        db.close()

    assert Base  # imported for clarity that models are registered

    resp = client.get("/needs-attention", headers=auth_header)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["gate"] == "rejection"
    assert rows[0]["status"] == "open"
    assert rows[0]["full_name"] == "Jane Doe"
