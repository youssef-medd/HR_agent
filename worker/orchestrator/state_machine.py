"""Application state machine (spec §2.1).

Encoded as a `StrEnum` plus an explicit `LEGAL` adjacency map. `transition`
raises `IllegalTransition` on any edge that is not in the map — the
orchestrator catches it and routes the application to `NEEDS_ATTENTION`.

Keeping the map explicit (rather than deriving it from graph edges) means the
state contract is auditable in one file and the test in
`tests/test_state_machine.py` can assert every reachable state is covered.
"""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    SCORED = "SCORED"
    SHORTLISTED = "SHORTLISTED"
    POOL = "POOL"
    DECLINE_PENDING = "DECLINE_PENDING"
    PRESCREENING = "PRESCREENING"
    PRESCREENED = "PRESCREENED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEWED = "INTERVIEWED"
    OFFER = "OFFER"
    HIRED = "HIRED"
    ONBOARDING = "ONBOARDING"
    DECLINED = "DECLINED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


LEGAL: dict[State, set[State]] = {
    State.RECEIVED: {State.PARSED, State.NEEDS_ATTENTION},
    State.PARSED: {State.SCORED, State.NEEDS_ATTENTION},
    State.SCORED: {
        State.SHORTLISTED,
        State.POOL,
        State.DECLINE_PENDING,
        State.NEEDS_ATTENTION,
    },
    State.SHORTLISTED: {State.PRESCREENING, State.NEEDS_ATTENTION},
    State.PRESCREENING: {State.PRESCREENED, State.NEEDS_ATTENTION},
    State.PRESCREENED: {State.INTERVIEW_SCHEDULED, State.NEEDS_ATTENTION},
    State.INTERVIEW_SCHEDULED: {State.INTERVIEWED, State.NEEDS_ATTENTION},
    State.INTERVIEWED: {State.OFFER, State.DECLINE_PENDING, State.NEEDS_ATTENTION},
    State.OFFER: {State.HIRED, State.DECLINED, State.NEEDS_ATTENTION},
    State.HIRED: {State.ONBOARDING, State.NEEDS_ATTENTION},
    State.DECLINE_PENDING: {State.DECLINED, State.NEEDS_ATTENTION},
    State.POOL: set(),
    State.ONBOARDING: set(),
    State.DECLINED: set(),
    State.NEEDS_ATTENTION: set(),
}

SENSITIVE_GATES: dict[State, str] = {
    State.DECLINE_PENDING: "rejection",
    State.OFFER: "offer",
}


class IllegalTransition(RuntimeError):
    def __init__(self, from_state: State, to_state: State) -> None:
        super().__init__(f"Illegal transition: {from_state} -> {to_state}")
        self.from_state = from_state
        self.to_state = to_state


def transition(current: State, requested: State) -> State:
    """Validate an edge. Return `requested` on success, else raise."""
    if requested in LEGAL.get(current, set()):
        return requested
    raise IllegalTransition(current, requested)


def is_terminal(state: State) -> bool:
    return not LEGAL.get(state, set())
