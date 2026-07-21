"""Cal.com webhook — BOOKING_CREATED resumes the paused application."""

from __future__ import annotations

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _no_secret(monkeypatch):
    monkeypatch.setattr(settings, "calcom_webhook_secret", "")  # signature check off


def _seed_prescreened(client) -> int:
    from app.db import get_db
    from app.models.application import Application

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row = Application(job_id=1, candidate_ref="cand@x.io", state="PRESCREENED", payload={})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _booking(app_id: int | str | None) -> dict:
    meta = {} if app_id is None else {"application_id": str(app_id)}
    return {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {"startTime": "2026-07-20T15:00:00Z", "metadata": meta},
    }


def test_booking_created_resumes_application(client, monkeypatch):
    from app.routers import calcom as calcom_router

    enqueued: list = []
    monkeypatch.setattr(calcom_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    app_id = _seed_prescreened(client)
    resp = client.post("/webhooks/calcom", json=_booking(app_id))

    assert resp.status_code == 200
    assert len(enqueued) == 1
    assert enqueued[0][0] == app_id
    assert "Cal.com" in enqueued[0][1]["candidate_message"]


def test_non_booking_event_ignored(client, monkeypatch):
    from app.routers import calcom as calcom_router

    enqueued: list = []
    monkeypatch.setattr(calcom_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    _seed_prescreened(client)
    resp = client.post("/webhooks/calcom", json={"triggerEvent": "BOOKING_CANCELLED", "payload": {}})

    assert resp.status_code == 200
    assert enqueued == []


def test_wrong_state_ignored(client, monkeypatch):
    from app.db import get_db
    from app.models.application import Application
    from app.routers import calcom as calcom_router

    enqueued: list = []
    monkeypatch.setattr(calcom_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row = Application(job_id=1, candidate_ref="c@x.io", state="RECEIVED", payload={})
        db.add(row)
        db.commit()
        db.refresh(row)
        app_id = row.id
    finally:
        db.close()

    resp = client.post("/webhooks/calcom", json=_booking(app_id))
    assert resp.status_code == 200
    assert enqueued == []


def test_signature_rejected_when_secret_set(client, monkeypatch):
    from app.routers import calcom as calcom_router

    monkeypatch.setattr(settings, "calcom_webhook_secret", "shh")
    enqueued: list = []
    monkeypatch.setattr(calcom_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a))

    app_id = _seed_prescreened(client)
    # No / wrong signature header -> ignored.
    resp = client.post("/webhooks/calcom", json=_booking(app_id), headers={"X-Cal-Signature-256": "bad"})
    assert resp.status_code == 200
    assert enqueued == []
