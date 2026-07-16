"""WhatsApp webhook tests — verify handshake + inbound message routing."""

from __future__ import annotations

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _verify_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "v-token")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")  # signature check off


def test_verify_echoes_challenge_on_match(client):
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "v-token", "hub.challenge": "12345"},
    )
    assert resp.status_code == 200
    assert resp.text == "12345"


def test_verify_rejects_bad_token(client):
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    )
    assert resp.status_code == 403


def _payload(from_phone: str, body: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "wba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": "wamid.abc",
                                    "timestamp": "1",
                                    "text": {"body": body},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_inbound_message_resumes_matching_application(client, monkeypatch):
    from app.db import get_db
    from app.models.application import Application
    from app.routers import whatsapp as whatsapp_router

    enqueued: list[tuple] = []
    monkeypatch.setattr(
        whatsapp_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a)
    )

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        row = Application(
            job_id=1, candidate_ref="17863559966", state="PRESCREENING", payload={}
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        app_id = row.id
    finally:
        db.close()

    resp = client.post("/webhooks/whatsapp", json=_payload("17863559966", "yes"))
    assert resp.status_code == 200
    assert enqueued == [(app_id, {"candidate_message": "yes"})]


def test_inbound_message_no_match_is_noop(client, monkeypatch):
    from app.routers import whatsapp as whatsapp_router

    enqueued: list[tuple] = []
    monkeypatch.setattr(
        whatsapp_router, "enqueue_application_step", lambda *a, **k: enqueued.append(a)
    )

    resp = client.post("/webhooks/whatsapp", json=_payload("10000000000", "hello"))
    assert resp.status_code == 200
    assert enqueued == []
