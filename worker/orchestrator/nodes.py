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
from orchestrator.agents.parser import CVParseError, extract_text, parse_cv
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


def _resolve_cv_text(payload: dict[str, Any]) -> str:
    """Turn the CV reference on an application's payload into plain text.

    Accepts, in priority order: pre-extracted `cv_text`; a base64 document
    (`cv_b64` + `cv_filename`) as produced by the upload endpoint; or a
    container-visible `cv_path`. Raises `CVParseError` when none is present.
    """
    if payload.get("cv_text"):
        return str(payload["cv_text"])

    filename = payload.get("cv_filename")
    if payload.get("cv_b64") and filename:
        import base64

        return extract_text(filename, base64.b64decode(payload["cv_b64"]))

    if payload.get("cv_path"):
        path = str(payload["cv_path"])
        with open(path, "rb") as fh:
            return extract_text(path, fh.read())

    raise CVParseError("No CV source on application payload (cv_text / cv_b64 / cv_path)")


def parse_node(db: Session, state: NodeState) -> NodeState:
    """A1 — extract structured CV data. Routes to NEEDS_ATTENTION on failure."""
    app_row = db.get(Application, state["application_id"])
    payload = dict(app_row.payload) if app_row is not None else {}

    def _work() -> dict[str, Any]:
        raw_text = _resolve_cv_text(payload)
        cv = parse_cv(raw_text, user_id=str(state["application_id"]))
        return cv.model_dump()

    try:
        parsed = with_ledger(
            db, state["application_id"], "parse", state.get("attempt", 1), _work
        )
    except CVParseError as exc:
        db.add(
            ApplicationEvent(
                application_id=state["application_id"],
                kind="parse_failed",
                step="parse",
                attempt=state.get("attempt", 1),
                payload={"error": str(exc)},
            )
        )
        return _advance(db, state, State.NEEDS_ATTENTION, "parse_failed")

    if app_row is not None:
        app_row.payload = {**app_row.payload, "cv": parsed}
    state.setdefault("scratch", {})["cv"] = parsed
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
