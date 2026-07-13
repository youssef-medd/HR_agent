"""The graph must stop at NEEDS_ATTENTION, not fall through to the next node.

Regression test for the linear-graph bug where a failed parse/score routed to
NEEDS_ATTENTION and the next node then attempted an illegal transition.
"""

from __future__ import annotations

from app.models.application import Application
from orchestrator.checkpointer import memory_saver
from orchestrator.graph import build_graph


def test_parse_failure_halts_at_needs_attention(db_factory):
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="x@y.z", state="RECEIVED", payload={})  # no CV
        db.add(row)
        db.commit()
        db.refresh(row)
        app_id = row.id

    graph = build_graph(db_factory, memory_saver())
    # Should NOT raise IllegalTransition — the graph halts at NEEDS_ATTENTION.
    result = graph.invoke(
        {"application_id": app_id, "stage": "RECEIVED", "attempt": 1},
        config={"configurable": {"thread_id": str(app_id)}},
    )
    assert result["stage"] == "NEEDS_ATTENTION"

    with db_factory() as db:
        assert db.get(Application, app_id).state == "NEEDS_ATTENTION"
