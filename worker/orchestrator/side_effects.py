"""Private side-effect implementations.

Every function here has a leading underscore. That is the contract enforced
by `tests/test_gates_static.py`: no module outside `orchestrator.gates` may
reference these names. The gate layer verifies the recruiter approval exists
before invoking the underscore function.

Real senders (SMTP, WhatsApp Cloud API, Cal.com, HR system) plug in here in
later slices. Slice 1 uses a small in-process "sent log" so tests can assert
exactly-once delivery.
"""

from __future__ import annotations

from typing import Any

# In-memory sent log — swapped for the real senders in later slices.
# Reset per test via the `_sent_log_reset` fixture.
_SENT: list[dict[str, Any]] = []


def _sent_log_reset() -> None:
    _SENT.clear()


def _sent_log_snapshot() -> list[dict[str, Any]]:
    return list(_SENT)


def _send_rejection_impl(application_id: int, recipient: str, template: str) -> dict[str, Any]:
    entry = {
        "kind": "rejection",
        "application_id": application_id,
        "recipient": recipient,
        "template": template,
    }
    _SENT.append(entry)
    return entry


def _send_offer_impl(application_id: int, recipient: str, template: str) -> dict[str, Any]:
    entry = {
        "kind": "offer",
        "application_id": application_id,
        "recipient": recipient,
        "template": template,
    }
    _SENT.append(entry)
    return entry


def _send_confirmation_impl(application_id: int, recipient: str) -> dict[str, Any]:
    entry = {
        "kind": "confirmation",
        "application_id": application_id,
        "recipient": recipient,
    }
    _SENT.append(entry)
    return entry


def _publish_job_impl(job_id: int, board: str) -> dict[str, Any]:
    entry = {"kind": "publish", "job_id": job_id, "board": board}
    _SENT.append(entry)
    return entry


def _send_whatsapp_impl(application_id: int, recipient: str, body: str) -> dict[str, Any]:
    """A5 pre-screening message. Non-sensitive (no recruiter gate) — called from
    `nodes.prescreen_node` through the idempotency ledger, like the confirmation
    sender. The real Meta WhatsApp Cloud API transport plugs in here later."""
    entry = {
        "kind": "whatsapp",
        "application_id": application_id,
        "recipient": recipient,
        "body": body,
    }
    _SENT.append(entry)
    return entry


def _send_booking_link_impl(application_id: int, recipient: str, link: str) -> dict[str, Any]:
    """A6 interview booking link. Non-sensitive — called from
    `nodes.schedule_node` through the idempotency ledger. The real Cal.com API
    (link creation + booking webhook) plugs in here later."""
    entry = {
        "kind": "booking_link",
        "application_id": application_id,
        "recipient": recipient,
        "link": link,
    }
    _SENT.append(entry)
    return entry
