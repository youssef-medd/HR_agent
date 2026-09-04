"""A6 interview lifecycle — slot pick, replan, cancellation, no-show.

Offline: the Celery hand-off (`enqueue_application_step` for the graph resume,
`enqueue_interview_update` for the candidate message) is monkeypatched, so these
assert the row-level contract the worker later acts on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import interviews
from app.db import get_db
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.needs_attention import NeedsAttention
from app.routers import public as public_router
from app.security import create_access_token


@pytest.fixture
def auth_header(admin_user) -> dict[str, str]:
    token = create_access_token(sub=str(admin_user.id), role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _stub_queue(monkeypatch):
    """Capture both hand-offs to the worker."""
    steps: list[tuple] = []
    updates: list[tuple] = []
    monkeypatch.setattr(public_router, "enqueue_application_step", lambda *a: steps.append(a))
    monkeypatch.setattr(interviews, "enqueue_interview_update", lambda *a: updates.append(a))
    return {"steps": steps, "updates": updates}


def _session(client):
    return next(client.app.dependency_overrides[get_db]())


def _seed(client, *, state: str, interview: dict | None = None) -> int:
    db = _session(client)
    try:
        row = Application(
            job_id=1,
            candidate_ref="cand@x.io",
            state=state,
            payload={"interview": interview} if interview else {},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _row(client, app_id: int) -> Application:
    db = _session(client)
    try:
        return db.get(Application, app_id)
    finally:
        db.close()


def _block(client, app_id: int) -> dict:
    return (_row(client, app_id).payload or {}).get("interview") or {}


def _events(client, app_id: int, kind: str) -> list[ApplicationEvent]:
    db = _session(client)
    try:
        return [
            e for e in db.query(ApplicationEvent)
            .filter(ApplicationEvent.application_id == app_id, ApplicationEvent.kind == kind)
            .all()
        ]
    finally:
        db.close()


def _attention(client, app_id: int, reason: str, status: str = "open") -> list[NeedsAttention]:
    db = _session(client)
    try:
        return (
            db.query(NeedsAttention)
            .filter(
                NeedsAttention.application_id == app_id,
                NeedsAttention.reason == reason,
                NeedsAttention.status == status,
            )
            .all()
        )
    finally:
        db.close()


def _slots(n: int = 3) -> list[str]:
    base = datetime.now(UTC) + timedelta(days=1)
    return [(base + timedelta(days=i)).replace(microsecond=0).isoformat() for i in range(n)]


# --- Slot picking -----------------------------------------------------------


def test_booking_view_lists_future_slots_only(client):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    future = _slots(2)
    app_id = _seed(client, state="PRESCREENED", interview={
        "link": "https://cal.com/book/1", "timezone": "UTC",
        "proposed_slots": [past, *future],
    })

    resp = client.get(f"/public/booking?email=cand@x.io&application_id={app_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert [s["at"] for s in body["slots"]] == future
    assert body["awaiting"] is True and body["booked"] is False
    assert body["can_reschedule"] is False


def test_confirm_stamps_the_picked_slot(client, _stub_queue):
    slots = _slots()
    app_id = _seed(client, state="PRESCREENED", interview={"timezone": "UTC", "proposed_slots": slots})

    resp = client.post(
        "/public/booking/confirm",
        json={"email": "cand@x.io", "application_id": app_id, "slot_at": slots[2]},
    )

    assert resp.status_code == 200
    block = _block(client, app_id)
    # The third slot, not the first — this is what the ICS is built from.
    assert interviews.parse_slot(block["scheduled_at"]) == interviews.parse_slot(slots[2])
    assert block["source"] == "portal"
    assert _stub_queue["steps"][0][0] == app_id
    assert len(_events(client, app_id, "interview_slot_picked")) == 1


def test_confirm_without_a_slot_still_resumes(client, _stub_queue):
    """A candidate who booked on the Cal.com page just tells us in free text."""
    app_id = _seed(client, state="PRESCREENED", interview={"proposed_slots": _slots()})

    resp = client.post(
        "/public/booking/confirm",
        json={"email": "cand@x.io", "application_id": app_id, "slot": "Tuesday 3pm"},
    )

    assert resp.status_code == 200
    assert "Tuesday 3pm" in _stub_queue["steps"][0][1]["candidate_message"]
    assert "scheduled_at" not in _block(client, app_id)


def test_confirm_rejects_a_malformed_slot(client):
    app_id = _seed(client, state="PRESCREENED", interview={"proposed_slots": _slots()})

    resp = client.post(
        "/public/booking/confirm",
        json={"email": "cand@x.io", "application_id": app_id, "slot_at": "not-a-date"},
    )

    assert resp.status_code == 422


# --- Reschedule -------------------------------------------------------------


def _booked(client, at: str | None = None) -> tuple[int, str]:
    slots = _slots()
    start = at or slots[0]
    app_id = _seed(client, state="INTERVIEW_SCHEDULED", interview={
        "booked": True, "timezone": "UTC", "sequence": 0, "reminder_sent": True,
        "scheduled_at": start, "when": "the booked time", "proposed_slots": slots,
        "link": "https://cal.com/book/1",
    })
    return app_id, slots[1]


def test_portal_reschedule_updates_the_row_and_queues_the_invite(client, _stub_queue):
    app_id, new_slot = _booked(client)

    resp = client.post(
        "/public/booking/reschedule",
        json={"email": "cand@x.io", "application_id": app_id, "slot_at": new_slot},
    )

    assert resp.status_code == 200
    block = _block(client, app_id)
    assert interviews.parse_slot(block["scheduled_at"]) == interviews.parse_slot(new_slot)
    # Sequence bump is what makes the replacement ICS supersede the first invite.
    assert block["sequence"] == 1
    assert block["reschedule_count"] == 1
    # The new time must get its own 24h reminder.
    assert block["reminder_sent"] is False
    assert block["history"][-1]["kind"] == "rescheduled"
    assert _stub_queue["updates"] == [(app_id, "reschedule")]
    assert len(_events(client, app_id, "interview_rescheduled")) == 1
    # The application stays INTERVIEW_SCHEDULED (the graph is on the offer gate).
    assert _row(client, app_id).state == "INTERVIEW_SCHEDULED"
    assert resp.json()["reschedule_count"] == 1


def test_portal_reschedule_rejects_a_past_slot(client):
    app_id, _ = _booked(client)
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

    resp = client.post(
        "/public/booking/reschedule",
        json={"email": "cand@x.io", "application_id": app_id, "slot_at": past},
    )

    assert resp.status_code == 422


def test_reschedule_without_a_booking_conflicts(client):
    app_id = _seed(client, state="PRESCREENED", interview={"proposed_slots": _slots()})

    resp = client.post(
        "/public/booking/reschedule",
        json={"email": "cand@x.io", "application_id": app_id, "slot_at": _slots()[1]},
    )

    assert resp.status_code == 409


def test_recruiter_reschedule(client, auth_header, _stub_queue):
    app_id, new_slot = _booked(client)

    resp = client.post(
        f"/applications/{app_id}/interview/reschedule",
        json={"start": new_slot, "reason": "panel clash"},
        headers=auth_header,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert interviews.parse_slot(body["scheduled_at"]) == interviews.parse_slot(new_slot)
    assert _stub_queue["updates"] == [(app_id, "reschedule")]
    assert _block(client, app_id)["history"][-1]["reason"] == "panel clash"


def test_interview_view_requires_auth(client):
    app_id, _ = _booked(client)
    assert client.get(f"/applications/{app_id}/interview").status_code == 401


# --- No-show / attended / cancel --------------------------------------------


def test_no_show_opens_one_attention_item_and_is_idempotent(client, auth_header, _stub_queue):
    app_id, _ = _booked(client)

    first = client.post(f"/applications/{app_id}/interview/no-show", headers=auth_header)
    second = client.post(f"/applications/{app_id}/interview/no-show", headers=auth_header)

    assert first.status_code == second.status_code == 200
    assert first.json()["no_show"] is True
    assert len(_attention(client, app_id, interviews.NO_SHOW_REASON)) == 1
    assert len(_events(client, app_id, "interview_no_show")) == 1
    assert _stub_queue["updates"] == [(app_id, "no_show")]
    # Still INTERVIEW_SCHEDULED — the miss is a queue item, not a state flip.
    assert _row(client, app_id).state == "INTERVIEW_SCHEDULED"


def test_rescheduling_after_a_no_show_closes_the_item(client, auth_header):
    app_id, new_slot = _booked(client)
    client.post(f"/applications/{app_id}/interview/no-show", headers=auth_header)

    resp = client.post(
        f"/applications/{app_id}/interview/reschedule",
        json={"start": new_slot},
        headers=auth_header,
    )

    assert resp.status_code == 200
    assert resp.json()["no_show"] is False
    assert _attention(client, app_id, interviews.NO_SHOW_REASON) == []
    closed = _attention(client, app_id, interviews.NO_SHOW_REASON, status="closed")
    assert closed[0].resolution["decision"] == "rescheduled"


def test_attended_closes_the_no_show_and_stops_the_sweep(client, auth_header):
    app_id, _ = _booked(client)
    client.post(f"/applications/{app_id}/interview/no-show", headers=auth_header)

    resp = client.post(f"/applications/{app_id}/interview/attended", headers=auth_header)

    assert resp.status_code == 200
    assert resp.json()["outcome"] == "attended"
    assert _attention(client, app_id, interviews.NO_SHOW_REASON) == []
    db = _session(client)
    try:
        assert interviews.due_no_shows(db, now=datetime.now(UTC) + timedelta(days=30)) == []
    finally:
        db.close()


def test_cancel_withdraws_and_queues_a_human(client, auth_header, _stub_queue):
    app_id, _ = _booked(client)

    resp = client.post(
        f"/applications/{app_id}/interview/cancel",
        json={"reason": "role on hold"},
        headers=auth_header,
    )

    assert resp.status_code == 200
    block = _block(client, app_id)
    assert block["booked"] is False and block["cancelled_at"]
    assert block["sequence"] == 1  # bumped so the CANCEL ICS supersedes the invite
    assert len(_attention(client, app_id, interviews.CANCELLED_REASON)) == 1
    assert _stub_queue["updates"] == [(app_id, "cancel")]


# --- The sweep --------------------------------------------------------------


def test_due_no_shows_waits_for_the_grace_window(client):
    start = datetime.now(UTC) - timedelta(minutes=10)
    app_id = _seed(client, state="INTERVIEW_SCHEDULED", interview={
        "booked": True, "scheduled_at": start.isoformat(),
    })

    db = _session(client)
    try:
        # 30min interview + 30min grace has not elapsed yet.
        assert interviews.due_no_shows(db, now=datetime.now(UTC)) == []
        due = interviews.due_no_shows(db, now=datetime.now(UTC) + timedelta(hours=2))
        assert [r.id for r in due] == [app_id]
    finally:
        db.close()


def test_due_no_shows_skips_cancelled_and_flagged_rows(client):
    long_past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    _seed(client, state="INTERVIEW_SCHEDULED", interview={
        "scheduled_at": long_past, "cancelled_at": long_past,
    })
    _seed(client, state="INTERVIEW_SCHEDULED", interview={
        "scheduled_at": long_past, "no_show": True,
    })
    _seed(client, state="INTERVIEW_SCHEDULED", interview={"scheduled_at": None})

    db = _session(client)
    try:
        assert interviews.due_no_shows(db) == []
    finally:
        db.close()
