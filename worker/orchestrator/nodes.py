"""Graph node bodies.

Every node here is a stub — no LLM inside. It advances the state machine,
writes an `application_event` row, and (for confirmation / notification-style
side effects) goes through the idempotency ledger. Real agent bodies land in
later slices; this file is the seam they plug into.

Contract: a node takes a `NodeState` (TypedDict), mutates it, and returns
either the new state or a LangGraph `Command` for gated transitions. It must
never call anything under `orchestrator.side_effects` directly — sensitive
work goes through `orchestrator.gates`.
"""

from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_event import ApplicationEvent
from orchestrator.gates import execute_after_rejection_gate, require_gate
from orchestrator.idempotency import with_ledger
from orchestrator.side_effects import _send_confirmation_impl
from orchestrator.state_machine import State, transition


class NodeState(TypedDict, total=False):
    application_id: int
    stage: str
    attempt: int
    scratch: dict[str, Any]


def _advance(db: Session, state: NodeState, to_state: State, step: str) -> NodeState:
    current = State(state["stage"])
    new = transition(current, to_state)
    state["stage"] = new.value

    app_row = db.get(Application, state["application_id"])
    if app_row is not None:
        app_row.state = new.value

    db.add(
        ApplicationEvent(
            application_id=state["application_id"],
            kind="transition",
            from_state=current.value,
            to_state=new.value,
            step=step,
            attempt=state.get("attempt", 1),
            payload={},
        )
    )
    db.commit()
    return state


def parse_node(db: Session, state: NodeState) -> NodeState:
    def _work() -> dict[str, Any]:
        return {"parsed": True}

    with_ledger(db, state["application_id"], "parse", state.get("attempt", 1), _work)
    return _advance(db, state, State.PARSED, "parse")


def score_node(db: Session, state: NodeState) -> NodeState:
    def _work() -> dict[str, Any]:
        return {"score": 0.0}

    result = with_ledger(db, state["application_id"], "score", state.get("attempt", 1), _work)
    state.setdefault("scratch", {})["score"] = result.get("score", 0.0)
    return _advance(db, state, State.SCORED, "score")


def send_confirmation_node(db: Session, state: NodeState) -> NodeState:
    """Non-sensitive notification — goes through the ledger, no gate."""

    app_row = db.get(Application, state["application_id"])
    recipient = (app_row.candidate_ref if app_row is not None else "unknown@example.com")

    def _work() -> dict[str, Any]:
        return _send_confirmation_impl(state["application_id"], recipient)

    with_ledger(
        db, state["application_id"], "send_confirmation", state.get("attempt", 1), _work
    )
    return state


def decline_pending_node(db: Session, state: NodeState) -> NodeState:
    return _advance(db, state, State.DECLINE_PENDING, "decline_pending")


def declined_node(db: Session, state: NodeState) -> NodeState:
    """Sensitive: requires a recruiter approval on the `rejection` gate."""

    decision = require_gate(db, state["application_id"], "rejection")
    app_row = db.get(Application, state["application_id"])
    recipient = app_row.candidate_ref if app_row is not None else "unknown@example.com"

    if decision.get("decision") == "approve":
        def _work() -> dict[str, Any]:
            return execute_after_rejection_gate(
                db, state["application_id"], recipient, "rejection@v1"
            )

        with_ledger(
            db, state["application_id"], "send_rejection", state.get("attempt", 1), _work
        )
        return _advance(db, state, State.DECLINED, "declined")

    return _advance(db, state, State.NEEDS_ATTENTION, "declined_rejected_by_human")
