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

from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.agents.onboarder import OnboardingError, generate_onboarding_kit
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.job import Job
from orchestrator.agents.masking import mask_cv
from orchestrator.agents.parser import CVData, CVParseError, extract_text, parse_cv
from orchestrator.agents.prescreen import (
    CONSENT_PROMPT,
    PrescreenError,
    interpret_answer,
    interpret_consent,
    screening_questions,
)
from orchestrator.agents.scheduler import (
    SchedulerError,
    booking_link,
    booking_prompt,
    interpret_booking_reply,
)
from orchestrator.agents.scorer import ScoreError, check_hard_filters, score_candidate
from orchestrator.gates import (
    execute_after_offer_gate,
    execute_after_rejection_gate,
    require_gate,
)
from orchestrator.idempotency import with_ledger
from orchestrator.side_effects import (
    _send_booking_link_impl,
    _send_confirmation_impl,
    _send_whatsapp_impl,
)
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
    """A4 — score the masked CV against the job description. NEEDS_ATTENTION on failure.

    Consumes A1's structured JobSpec when present: the eliminatory criteria act
    as hard filters (any unmet -> forced decline, routed to the human rejection
    gate) and the per-job weights drive the weighted overall.
    """
    app_id = state["application_id"]
    app_row = db.get(Application, app_id)
    payload = dict(app_row.payload) if app_row is not None else {}

    job = db.get(Job, app_row.job_id) if app_row is not None else None
    job_spec = (job.spec or {}) if job is not None else {}
    eliminatory = (job_spec.get("spec") or {}).get("eliminatory_criteria") or []
    weights = job_spec.get("weights")

    def _work() -> dict[str, Any]:
        cv = CVData.model_validate(payload.get("cv") or {})
        masked = mask_cv(cv)
        unmet = check_hard_filters(masked, eliminatory, user_id=str(app_id))
        result = score_candidate(
            masked, payload.get("jd_text"), weights=weights, user_id=str(app_id)
        )
        data = result.model_dump()
        data["weights_used"] = weights or "default"
        if unmet:
            # Hard-filter failure overrides the judge: decline (human-gated),
            # never auto-sent. Recorded for the recruiter to see the reason.
            data["recommendation"] = "decline"
            data["hard_filter_failures"] = unmet
        return data

    try:
        score = with_ledger(db, state["application_id"], "score", state.get("attempt", 1), _work)
    except ScoreError as exc:
        db.add(
            ApplicationEvent(
                application_id=state["application_id"],
                kind="score_failed",
                step="score",
                attempt=state.get("attempt", 1),
                payload={"error": str(exc)},
            )
        )
        return _advance(db, state, State.NEEDS_ATTENTION, "score_failed")

    if app_row is not None:
        app_row.payload = {**app_row.payload, "score": score}
    scratch = state.setdefault("scratch", {})
    scratch["score"] = score.get("overall", 0)
    scratch["recommendation"] = score.get("recommendation", "pool")
    return _advance(db, state, State.SCORED, "score")


def shortlisted_node(db: Session, state: NodeState) -> NodeState:
    return _advance(db, state, State.SHORTLISTED, "shortlisted")


def pool_node(db: Session, state: NodeState) -> NodeState:
    return _advance(db, state, State.POOL, "pool")


def send_confirmation_node(db: Session, state: NodeState) -> NodeState:
    """Non-sensitive acknowledgement — goes through the ledger, no gate.

    Best-effort: the confirmation is a courtesy, not a pipeline dependency, so a
    delivery failure (e.g. a WhatsApp candidate outside the 24h window, or a bad
    address) is logged and swallowed — it must never block scoring/shortlisting.
    """
    app_id = state["application_id"]
    attempt = state.get("attempt", 1)
    app_row = db.get(Application, app_id)
    recipient = app_row.candidate_ref if app_row is not None else "unknown@example.com"

    def _work() -> dict[str, Any]:
        return _send_confirmation_impl(app_id, recipient)

    try:
        with_ledger(db, app_id, "send_confirmation", attempt, _work)
    except Exception as exc:  # noqa: BLE001 — courtesy send must not brick the graph
        db.rollback()
        db.add(
            ApplicationEvent(
                application_id=app_id,
                kind="confirmation_failed",
                step="send_confirmation",
                attempt=attempt,
                payload={"error": str(exc)},
            )
        )
        db.commit()
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


def _candidate_message(resume: Any) -> str:
    """Pull the candidate's text out of the resume event fed by the reply path."""
    if isinstance(resume, dict):
        return str(resume.get("candidate_message", ""))
    return str(resume)


def _save_payload_key(db: Session, application_id: int, key: str, block: dict[str, Any]) -> None:
    """Persist one payload key from an INDEPENDENT session.

    Payload writes committed on the node's own session do not survive when the
    node later raises `interrupt()` (LangGraph replays the node and the pause
    discards the in-flight session's work). A fresh session bound to the same
    engine commits in its own transaction, so mid-conversation state (chat
    transcript, answers, booking link) is durable while the graph is paused.
    """
    with Session(bind=db.get_bind()) as s:
        row = s.get(Application, application_id)
        if row is not None:
            row.payload = {**row.payload, key: block}
            s.commit()


def _save_prescreen(db: Session, application_id: int, block: dict[str, Any]) -> None:
    _save_payload_key(db, application_id, "prescreen", block)


def _save_interview(db: Session, application_id: int, block: dict[str, Any]) -> None:
    _save_payload_key(db, application_id, "interview", block)


def _resolve_phone(payload: dict[str, Any]) -> str:
    return (payload.get("phone") or (payload.get("cv") or {}).get("phone") or "").strip()


def _whatsapp_recipient(app_row: Application | None, payload: dict[str, Any]) -> str:
    """Resolve the WhatsApp number for a candidate.

    Prefers the phone captured on the application (apply form), then the phone
    parsed from the CV, and only falls back to `candidate_ref` (which may be an
    email — the send will then fail loudly rather than silently mis-target).
    """
    if app_row is None:
        return "unknown"
    return _resolve_phone(payload) or app_row.candidate_ref


def _prescreen_channel(payload: dict[str, Any]) -> str:
    """A5 delivery channel: WhatsApp when a real phone is on file, else web chat.

    Web candidates (apply form / email intake with no phone) pre-screen through
    the candidate portal; the transcript on the payload is the delivery surface.
    """
    return "whatsapp" if _resolve_phone(payload) else "web"


def prescreen_node(db: Session, state: NodeState) -> NodeState:
    """A5 — WhatsApp conversational pre-screening.

    Multi-turn: each candidate reply arrives as a separate resume, so this body
    re-executes top-to-bottom on every turn. Two invariants make the replay
    safe:

    - The transition into PRESCREENING is guarded on the *DB row* state (the
      source of truth), never on `state["stage"]` — LangGraph replays the node
      from its checkpointed input (`SHORTLISTED`) each time, so a state-based
      guard would re-fire the transition on every turn.
    - The `interrupt()` sequence is deterministic — consent, then one per
      question in order — so LangGraph feeds resume values back positionally.
      Sends go through the ledger (exactly-once); answers are rebuilt from the
      resume values, with first-seen timestamps reused from the persisted block.
    """
    app_id = state["application_id"]
    attempt = state.get("attempt", 1)
    app_row = db.get(Application, app_id)
    payload = dict(app_row.payload) if app_row is not None else {}
    recipient = _whatsapp_recipient(app_row, payload)
    channel = _prescreen_channel(payload)

    # Keep the in-memory stage in lockstep with the DB so the final transition is
    # computed from the real current state on the completing replay.
    if app_row is not None:
        state["stage"] = app_row.state

    # First entry only: SHORTLISTED -> PRESCREENING. Skipped on every replay
    # because the DB row is already PRESCREENING by then.
    if State(state["stage"]) == State.SHORTLISTED:
        _advance(db, state, State.PRESCREENING, "prescreen_start")

    block: dict[str, Any] = dict(payload.get("prescreen") or {})
    prior_answers: list[dict[str, Any]] = list(block.get("answers") or [])
    questions = screening_questions(payload)

    # Transcript is rebuilt deterministically from the resume values on every
    # replay, so it can be regenerated fresh each turn. It is the web-chat
    # delivery surface (read by the portal) and an audit record for WhatsApp.
    transcript: list[dict[str, str]] = []
    block["channel"] = channel

    def _deliver(step: str, body: str) -> None:
        """Record an assistant message and send it over WhatsApp when applicable."""
        transcript.append({"role": "assistant", "text": body})
        block["transcript"] = list(transcript)
        _save_prescreen(db, app_id, block)  # persist so the web chat sees it while paused
        if channel == "whatsapp":
            with_ledger(
                db, app_id, step, attempt,
                lambda: _send_whatsapp_impl(app_id, recipient, body),
            )

    # --- Consent turn -------------------------------------------------------
    block.setdefault("status", "awaiting_consent")
    _deliver("prescreen_consent", CONSENT_PROMPT)
    consent_reply = _candidate_message(
        interrupt({"kind": "await_candidate_reply", "stage": "consent", "application_id": app_id})
    )
    transcript.append({"role": "user", "text": consent_reply})
    try:
        consent = interpret_consent(consent_reply, user_id=str(app_id))
    except PrescreenError as exc:
        block["status"] = "no_consent"
        block.setdefault("consent", {})["given"] = None
        block["transcript"] = list(transcript)
        _save_prescreen(db, app_id, block)
        db.add(ApplicationEvent(
            application_id=app_id, kind="prescreen_failed", step="prescreen_consent",
            attempt=attempt, payload={"error": str(exc)},
        ))
        return _advance(db, state, State.NEEDS_ATTENTION, "prescreen_no_consent")

    if not consent.consent:
        block["status"] = "no_consent"
        block["consent"] = {"given": False, "at": None}
        block["transcript"] = list(transcript)
        _save_prescreen(db, app_id, block)
        return _advance(db, state, State.NEEDS_ATTENTION, "prescreen_no_consent")

    consent_at = (block.get("consent") or {}).get("at") or datetime.now(UTC).isoformat()
    block["consent"] = {"given": True, "at": consent_at}
    block["status"] = "asking"
    _save_prescreen(db, app_id, block)

    # --- Question turns -----------------------------------------------------
    answers: list[dict[str, Any]] = []
    for i, question in enumerate(questions):
        _deliver(f"prescreen_q{i}", question)
        reply = _candidate_message(
            interrupt({
                "kind": "await_candidate_reply", "stage": "question",
                "idx": i, "application_id": app_id,
            })
        )
        transcript.append({"role": "user", "text": reply})
        try:
            interp = interpret_answer(question, reply, user_id=str(app_id))
        except PrescreenError as exc:
            block["answers"] = answers
            block["status"] = "error"
            block["transcript"] = list(transcript)
            _save_prescreen(db, app_id, block)
            db.add(ApplicationEvent(
                application_id=app_id, kind="prescreen_failed", step=f"prescreen_q{i}",
                attempt=attempt, payload={"error": str(exc)},
            ))
            return _advance(db, state, State.NEEDS_ATTENTION, "prescreen_answer_failed")

        answered_at = prior_answers[i]["at"] if i < len(prior_answers) else datetime.now(UTC).isoformat()
        answers.append({"q": question, "a": interp.answer, "at": answered_at})
        block["answers"] = answers
        block["idx"] = i + 1
        block["transcript"] = list(transcript)
        _save_prescreen(db, app_id, block)

    transcript.append({"role": "assistant", "text": "Thanks — that's everything. Our team will be in touch."})
    block["transcript"] = list(transcript)
    block["status"] = "done"
    _save_prescreen(db, app_id, block)
    return _advance(db, state, State.PRESCREENED, "prescreen")


def schedule_node(db: Session, state: NodeState) -> NodeState:
    """A6 — interview scheduling.

    Sends a Cal.com booking link (stubbed) and pauses until the candidate
    confirms a booked slot, then advances PRESCREENED -> INTERVIEW_SCHEDULED. A
    single interrupt keeps the replay deterministic; the send is ledger-guarded
    (exactly-once) and there is no pre-interrupt transition, so the application
    simply rests at PRESCREENED while awaiting the booking reply.
    """
    app_id = state["application_id"]
    attempt = state.get("attempt", 1)
    app_row = db.get(Application, app_id)
    payload = dict(app_row.payload) if app_row is not None else {}
    recipient = _whatsapp_recipient(app_row, payload)
    channel = _prescreen_channel(payload)

    if app_row is not None:
        state["stage"] = app_row.state

    link = booking_link(app_id)
    message = booking_prompt(link)
    # Persist the booking link so a web candidate can open it from the portal;
    # only send over WhatsApp when a real phone is on file (an email recipient
    # would 400 the Meta API).
    booking_block = dict(payload.get("interview") or {})
    booking_block["link"] = link
    booking_block["channel"] = channel
    _save_interview(db, app_id, booking_block)
    if channel == "whatsapp":
        with_ledger(
            db, app_id, "send_booking_link", attempt,
            lambda: _send_booking_link_impl(app_id, recipient, link, message),
        )
    reply = _candidate_message(
        interrupt({"kind": "await_booking", "application_id": app_id, "link": link})
    )

    interview = dict(payload.get("interview") or {})
    try:
        conf = interpret_booking_reply(reply, user_id=str(app_id))
    except SchedulerError as exc:
        interview.update(booked=False, link=link)
        _save_interview(db, app_id, interview)
        db.add(ApplicationEvent(
            application_id=app_id, kind="schedule_failed", step="send_booking_link",
            attempt=attempt, payload={"error": str(exc)},
        ))
        return _advance(db, state, State.NEEDS_ATTENTION, "schedule_failed")

    if not conf.confirmed:
        interview.update(booked=False, link=link)
        _save_interview(db, app_id, interview)
        return _advance(db, state, State.NEEDS_ATTENTION, "schedule_not_booked")

    booked_at = interview.get("at") or datetime.now(UTC).isoformat()
    interview.update(booked=True, when=conf.when, link=link, at=booked_at)
    _save_interview(db, app_id, interview)
    return _advance(db, state, State.INTERVIEW_SCHEDULED, "schedule")


def interview_node(db: Session, state: NodeState) -> NodeState:
    """A7 — post-interview recruiter decision through the sensitive offer gate.

    The interview itself is human-led; this node pauses on `require_gate("offer")`
    until a recruiter records the outcome. Approve → the candidate is marked
    interviewed, an offer email goes out (via the offer gate), and the state
    advances to HIRED. Reject → interviewed, then NEEDS_ATTENTION (no hire).

    Gate-first (like `declined_node`): the interrupt precedes every transition,
    so the replayed node advances exactly once on resume.
    """
    app_id = state["application_id"]
    attempt = state.get("attempt", 1)

    decision = require_gate(db, app_id, "offer")
    app_row = db.get(Application, app_id)
    recipient = app_row.candidate_ref if app_row is not None else "unknown@example.com"

    _advance(db, state, State.INTERVIEWED, "interviewed")

    if decision.get("decision") == "approve":
        _advance(db, state, State.OFFER, "offer")

        def _work() -> dict[str, Any]:
            return execute_after_offer_gate(db, app_id, recipient, "offer@v1")

        with_ledger(db, app_id, "send_offer", attempt, _work)
        return _advance(db, state, State.HIRED, "hired")

    return _advance(db, state, State.NEEDS_ATTENTION, "not_hired")


def onboarding_node(db: Session, state: NodeState) -> NodeState:
    """A8 — generate the onboarding kit for a hired candidate, then ONBOARDING."""
    app_id = state["application_id"]
    attempt = state.get("attempt", 1)
    app_row = db.get(Application, app_id)
    payload = dict(app_row.payload) if app_row is not None else {}

    job = db.get(Job, app_row.job_id) if app_row is not None else None
    role_title = job.title if job is not None else "New role"
    department = job.department if job is not None else None
    candidate_name = (payload.get("cv") or {}).get("full_name") or None

    def _work() -> dict[str, Any]:
        kit = generate_onboarding_kit(
            role_title=role_title,
            department=department,
            candidate_name=candidate_name,
            user_id=str(app_id),
        )
        return kit.model_dump()

    try:
        kit = with_ledger(db, app_id, "onboarding", attempt, _work)
    except OnboardingError as exc:
        db.add(
            ApplicationEvent(
                application_id=app_id,
                kind="onboarding_failed",
                step="onboarding",
                attempt=attempt,
                payload={"error": str(exc)},
            )
        )
        return _advance(db, state, State.NEEDS_ATTENTION, "onboarding_failed")

    if app_row is not None:
        app_row.payload = {**app_row.payload, "onboarding": kit}
    return _advance(db, state, State.ONBOARDING, "onboarding")
