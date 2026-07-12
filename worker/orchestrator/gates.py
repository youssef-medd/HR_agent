"""Sensitive human gates.

Every rejection, offer, and external publish must pass through this module.
The static test `tests/test_gates_static.py` walks every `.py` file under
`orchestrator/` and asserts that the symbols `_send_rejection_impl`,
`_send_offer_impl`, and `_publish_job_impl` are only referenced from this
file. That is the sole enforcement — the naming discipline is the audit
surface.

Flow:
    1. Orchestrator reaches a sensitive state.
    2. `require_gate` inserts a `NeedsAttention` row (status='open',
       gate=<name>) and calls LangGraph `interrupt()`. The graph pauses.
    3. A recruiter action calls `resume_with_decision(...)` via the API,
       which closes the row and returns the decision.
    4. `execute_after_*_gate` is called with the decision + the freshly
       closed row's id; it verifies status='closed' and
       resolution['decision'] == 'approve', then invokes the private impl.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.needs_attention import NeedsAttention
from orchestrator.side_effects import (
    _publish_job_impl,
    _send_offer_impl,
    _send_rejection_impl,
)


class GateNotApproved(RuntimeError):
    pass


def require_gate(
    db: Session,
    application_id: int,
    gate_name: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # LangGraph re-executes the whole node body on resume, so require_gate runs
    # a second time after the recruiter's decision. Reuse the row created on the
    # pre-interrupt pass rather than inserting a phantom duplicate — otherwise
    # every completed gate leaves an orphaned status='open' row behind.
    row = db.scalar(
        select(NeedsAttention)
        .where(
            NeedsAttention.application_id == application_id,
            NeedsAttention.gate == gate_name,
        )
        .order_by(NeedsAttention.created_at.desc())
    )
    if row is None:
        row = NeedsAttention(
            application_id=application_id,
            reason="sensitive_gate",
            gate=gate_name,
            context=context or {},
            status="open",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    decision: dict[str, Any] = interrupt(
        {
            "kind": "sensitive_gate",
            "gate": gate_name,
            "application_id": application_id,
            "needs_attention_id": row.id,
        }
    )
    return decision


def resume_with_decision(
    db: Session,
    application_id: int,
    gate_name: str,
    decision: str,
    resolved_by: str,
    payload: dict[str, Any] | None = None,
) -> NeedsAttention:
    row = db.scalar(
        select(NeedsAttention)
        .where(
            NeedsAttention.application_id == application_id,
            NeedsAttention.gate == gate_name,
            NeedsAttention.status == "open",
        )
        .order_by(NeedsAttention.created_at.desc())
    )
    if row is None:
        raise GateNotApproved(
            f"No open gate '{gate_name}' for application {application_id}"
        )
    row.status = "closed"
    row.resolved_by = resolved_by
    row.resolution = {"decision": decision, **(payload or {})}
    row.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def _assert_approved(db: Session, application_id: int, gate_name: str) -> NeedsAttention:
    row = db.scalar(
        select(NeedsAttention)
        .where(
            NeedsAttention.application_id == application_id,
            NeedsAttention.gate == gate_name,
            NeedsAttention.status == "closed",
        )
        .order_by(NeedsAttention.created_at.desc())
    )
    if row is None:
        raise GateNotApproved(
            f"No closed gate '{gate_name}' for application {application_id}"
        )
    resolution = row.resolution or {}
    if resolution.get("decision") != "approve":
        raise GateNotApproved(
            f"Gate '{gate_name}' for application {application_id} was rejected"
        )
    return row


def execute_after_rejection_gate(
    db: Session, application_id: int, recipient: str, template: str
) -> dict[str, Any]:
    _assert_approved(db, application_id, "rejection")
    return _send_rejection_impl(application_id, recipient, template)


def execute_after_offer_gate(
    db: Session, application_id: int, recipient: str, template: str
) -> dict[str, Any]:
    _assert_approved(db, application_id, "offer")
    return _send_offer_impl(application_id, recipient, template)


def execute_after_publish_gate(db: Session, application_id: int, job_id: int, board: str) -> dict[str, Any]:
    _assert_approved(db, application_id, "publish")
    return _publish_job_impl(job_id, board)
