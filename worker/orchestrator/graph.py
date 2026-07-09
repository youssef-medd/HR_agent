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
    parse_node,
    score_node,
    send_confirmation_node,
)


def build_graph(db_factory: Callable[[], Session], checkpointer: Any) -> Any:
    def _wrap(fn: Callable[[Session, NodeState], NodeState]):
        def _run(state: NodeState) -> NodeState:
            with db_factory() as db:
                return fn(db, state)

        return _run

    graph = StateGraph(NodeState)

    graph.add_node("parse", _wrap(parse_node))
    graph.add_node("score", _wrap(score_node))
    graph.add_node("send_confirmation", _wrap(send_confirmation_node))
    graph.add_node("decline_pending", _wrap(decline_pending_node))
    graph.add_node("declined", _wrap(declined_node))

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "score")
    graph.add_edge("score", "send_confirmation")
    graph.add_edge("send_confirmation", "decline_pending")
    graph.add_edge("decline_pending", "declined")
    graph.add_edge("declined", END)

    return graph.compile(checkpointer=checkpointer)
