"""RGPD erasure + retention (spec §7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _db(client):
    from app.db import get_db

    return next(client.app.dependency_overrides[get_db]())


def _seed_app(client, *, email="cand@x.io", created_at=None, state="SCORED"):
    from app.models.application import Application
    from app.models.message_log import MessageLog

    db = _db(client)
    try:
        row = Application(
            job_id=1, candidate_ref=email, state=state,
            payload={
                "applicant_name": "Jane Doe", "phone": "+21620000000",
                "cv": {"full_name": "Jane Doe", "email": email},
                "jd_text": "Backend role", "score": {"overall": 88},
            },
        )
        if created_at is not None:
            row.created_at = created_at
        db.add(row)
        db.commit()
        db.refresh(row)
        db.add(MessageLog(
            application_id=row.id, recipient=email, channel="email",
            template_id="offer", rendered_body="Your offer, Jane", status="sent",
        ))
        db.commit()
        return row.id
    finally:
        db.close()


def test_anonymize_scrubs_pii_keeps_audit(client):
    from app.models.application import Application
    from app.models.message_log import MessageLog
    from app.rgpd import erase_candidate

    app_id = _seed_app(client)
    db = _db(client)
    try:
        n = erase_candidate(db, "cand@x.io")
        assert n == 1
        row = db.get(Application, app_id)
        assert row.payload["erased"] is True
        assert "cv" not in row.payload and "applicant_name" not in row.payload
        assert row.payload["score"]["overall"] == 88  # audit signal retained
        assert row.candidate_ref.endswith("@redacted.invalid")
        msgs = db.query(MessageLog).all()
        assert all(m.recipient == "[erased]" and m.rendered_body == "[erased]" for m in msgs)
    finally:
        db.close()


def test_erase_is_idempotent(client):
    from app.rgpd import erase_candidate

    _seed_app(client)
    db = _db(client)
    try:
        assert erase_candidate(db, "cand@x.io") == 1
        # ref is now redacted; a second call by the original email matches nothing
        assert erase_candidate(db, "cand@x.io") == 0
    finally:
        db.close()


def test_purge_expired_anonymizes_old_only(client):
    from app.models.application import Application
    from app.rgpd import purge_expired

    old = _seed_app(client, email="old@x.io", created_at=datetime.now(UTC) - timedelta(days=400))
    recent = _seed_app(client, email="new@x.io", created_at=datetime.now(UTC) - timedelta(days=10))

    db = _db(client)
    try:
        purged = purge_expired(db, months=12)
        assert purged == [old]
        assert db.get(Application, old).payload["erased"] is True
        assert db.get(Application, recent).payload.get("erased") is None
    finally:
        db.close()


def test_erase_endpoint_verifies_ownership(client):
    app_id = _seed_app(client)

    # wrong email -> 404
    bad = client.post(
        "/public/candidates/erase", json={"email": "no@one.io", "application_id": app_id}
    )
    assert bad.status_code == 404

    ok = client.post(
        "/public/candidates/erase", json={"email": "cand@x.io", "application_id": app_id}
    )
    assert ok.status_code == 200
    assert ok.json() == {"erased": True, "applications_erased": 1}
