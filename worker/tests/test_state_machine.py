"""State machine invariants.

Every state reachable from RECEIVED has an entry in the LEGAL map. Every
legal transition is accepted; every illegal one raises. Terminal states
(POOL, ONBOARDING, DECLINED, NEEDS_ATTENTION) have no outgoing edges.
"""

from __future__ import annotations

import pytest

from orchestrator.state_machine import (
    LEGAL,
    IllegalTransition,
    State,
    is_terminal,
    transition,
)


def _reachable(start: State) -> set[State]:
    seen: set[State] = set()
    stack = [start]
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen.add(s)
        for nxt in LEGAL.get(s, set()):
            stack.append(nxt)
    return seen


def test_every_reachable_state_has_an_entry():
    for state in _reachable(State.RECEIVED):
        assert state in LEGAL, f"{state} missing from LEGAL"


def test_terminal_states_have_no_outgoing_edges():
    for terminal in (State.POOL, State.ONBOARDING, State.DECLINED, State.NEEDS_ATTENTION):
        assert is_terminal(terminal)
        with pytest.raises(IllegalTransition):
            transition(terminal, State.PARSED)


def test_legal_transitions_accepted():
    assert transition(State.RECEIVED, State.PARSED) == State.PARSED
    assert transition(State.PARSED, State.SCORED) == State.SCORED
    assert transition(State.SCORED, State.SHORTLISTED) == State.SHORTLISTED
    assert transition(State.INTERVIEWED, State.OFFER) == State.OFFER


def test_illegal_transitions_raise():
    with pytest.raises(IllegalTransition):
        transition(State.RECEIVED, State.HIRED)
    with pytest.raises(IllegalTransition):
        transition(State.PARSED, State.OFFER)
    with pytest.raises(IllegalTransition):
        transition(State.OFFER, State.RECEIVED)


def test_any_state_can_land_in_needs_attention():
    for state in _reachable(State.RECEIVED):
        if is_terminal(state):
            continue
        assert State.NEEDS_ATTENTION in LEGAL[state], f"{state} cannot escape to NEEDS_ATTENTION"
