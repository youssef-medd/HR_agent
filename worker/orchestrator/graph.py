"""LangGraph StateGraph assembly.

Builds the supervisor graph that A0 owns. Sensitive edges pass through
`gates.require_gate` (via the corresponding node in `nodes.py`), so the
graph itself has no direct reference to any private side-effect symbol.

The compiled graph is memoized by checkpointer instance so unit tests can
pass a `MemorySaver` while production wires a `PostgresSaver`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from orchestrator.nodes import (
    NodeState,
    decline_pending_node,
    declined_node,
    interview_node,
    onboarding_node,
    parse_node,
    pool_node,
    prescreen_node,
    schedule_node,
    score_node,
    send_confirmation_node,
    shortlisted_node,
)


def build_graph(db_factory: Callable[[], Session], checkpointer: Any) -> Any:
    def _wrap(fn: Callable[[Session, NodeState], NodeState]):
        def _run(state: NodeState) -> NodeState:
            with db_factory() as db:
                return fn(db, state)

        return _run

    # A node that fails routes the application to NEEDS_ATTENTION. The graph
    # must stop there rather than fall through to the next linear step (which
    # would attempt an illegal transition out of NEEDS_ATTENTION).
    def _halt_if_needs_attention(next_node: str) -> Callable[[NodeState], str]:
        def _route(state: NodeState) -> str:
            return END if state.get("stage") == "NEEDS_ATTENTION" else next_node

        return _route

    # After confirmation, the judge's recommendation routes the application:
    # shortlist -> SHORTLISTED, pool -> POOL, decline -> the human rejection gate.
    def _route_by_recommendation(state: NodeState) -> str:
        rec = (state.get("scratch") or {}).get("recommendation", "pool")
        return {"shortlist": "shortlisted", "pool": "pool"}.get(rec, "decline_pending")

    # After the offer gate: a hire flows into A8 onboarding; a no-hire ends at
    # NEEDS_ATTENTION.
    def _route_after_interview(state: NodeState) -> str:
        return "onboarding" if state.get("stage") == "HIRED" else END

    graph = StateGraph(NodeState)

    graph.add_node("parse", _wrap(parse_node))
    graph.add_node("score", _wrap(score_node))
    graph.add_node("send_confirmation", _wrap(send_confirmation_node))
    graph.add_node("shortlisted", _wrap(shortlisted_node))
    graph.add_node("prescreen", _wrap(prescreen_node))
    graph.add_node("schedule", _wrap(schedule_node))
    graph.add_node("interview", _wrap(interview_node))
    graph.add_node("onboarding", _wrap(onboarding_node))
    graph.add_node("pool", _wrap(pool_node))
    graph.add_node("decline_pending", _wrap(decline_pending_node))
    graph.add_node("declined", _wrap(declined_node))

    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", _halt_if_needs_attention("score"), {END: END, "score": "score"})
    graph.add_conditional_edges(
        "score",
        _halt_if_needs_attention("send_confirmation"),
        {END: END, "send_confirmation": "send_confirmation"},
    )
    graph.add_conditional_edges(
        "send_confirmation",
        _route_by_recommendation,
        {"shortlisted": "shortlisted", "pool": "pool", "decline_pending": "decline_pending"},
    )
    # A shortlisted candidate flows into A5 pre-screening (pauses awaiting the
    # consent reply). On PRESCREENED it continues into A6 scheduling (pauses
    # awaiting the booking reply); a no-consent PRESCREEN halts at
    # NEEDS_ATTENTION. After scheduling, A7 pauses on the offer gate for the
    # recruiter's post-interview decision; an approval extends the offer, marks
    # HIRED, and flows into A8 onboarding (-> ONBOARDING).
    graph.add_edge("shortlisted", "prescreen")
    graph.add_conditional_edges(
        "prescreen", _halt_if_needs_attention("schedule"), {END: END, "schedule": "schedule"}
    )
    graph.add_conditional_edges(
        "schedule", _halt_if_needs_attention("interview"), {END: END, "interview": "interview"}
    )
    graph.add_conditional_edges(
        "interview", _route_after_interview, {END: END, "onboarding": "onboarding"}
    )
    graph.add_edge("onboarding", END)
    graph.add_edge("pool", END)
    graph.add_edge("decline_pending", "declined")
    graph.add_edge("declined", END)

    return graph.compile(checkpointer=checkpointer)
