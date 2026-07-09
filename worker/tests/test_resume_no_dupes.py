"""AC #1 — kill mid-batch, resume, zero duplicates.

Runs a batch of 50 applications through the graph twice with the *same*
checkpointer and the *same* idempotency ledger. The second run is a proxy
for restart-after-crash: every node re-executes, but the ledger short-circuits
side effects that already succeeded.

Success criterion: `send_confirmation` (the only side-effect wired into the
Slice-1 skeleton) fires exactly once per application.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.application import Application
from app.models.needs_attention import NeedsAttention
from orchestrator.checkpointer import memory_saver
from orchestrator.graph import build_graph
from orchestrator.side_effects import _sent_log_reset, _sent_log_snapshot


BATCH = 50


def _seed_applications(db_factory) -> list[int]:
    ids: list[int] = []
    with db_factory() as db:
        for i in range(BATCH):
            row = Application(
                job_id=1,
                candidate_ref=f"cand-{i}@example.com",
                state="RECEIVED",
                payload={},
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    return ids


def _resolve_all_rejection_gates(db_factory, decision: str = "approve") -> None:
    from orchestrator.gates import resume_with_decision

    with db_factory() as db:
        rows = db.scalars(
            select(NeedsAttention).where(
                NeedsAttention.gate == "rejection",
                NeedsAttention.status == "open",
            )
        ).all()
        for row in rows:
            resume_with_decision(
                db, row.application_id, "rejection", decision, resolved_by="test"
            )


def _run_batch(db_factory, saver, ids: list[int]) -> None:
    graph = build_graph(db_factory, saver)
    for app_id in ids:
        config = {"configurable": {"thread_id": str(app_id)}}
        try:
            graph.invoke(
                {"application_id": app_id, "stage": "RECEIVED", "attempt": 1},
                config=config,
            )
        except Exception:
            # Sensitive gates surface as interrupts — for the test we resolve them
            # out of band and re-invoke below.
            continue


def test_kill_midbatch_restart_zero_duplicates(db_factory):
    _sent_log_reset()
    saver = memory_saver()
    ids = _seed_applications(db_factory)

    _run_batch(db_factory, saver, ids)
    _resolve_all_rejection_gates(db_factory, decision="approve")
    _run_batch(db_factory, saver, ids)

    _run_batch(db_factory, saver, ids)

    sent = _sent_log_snapshot()

    confirmations = [s for s in sent if s["kind"] == "confirmation"]
    assert len(confirmations) == BATCH, (
        f"expected {BATCH} confirmations, got {len(confirmations)}"
    )
    unique_recipients = {s["application_id"] for s in confirmations}
    assert len(unique_recipients) == BATCH, "duplicate confirmations detected"

    rejections = [s for s in sent if s["kind"] == "rejection"]
    unique_rejections = {s["application_id"] for s in rejections}
    assert len(rejections) == len(unique_rejections), "duplicate rejections detected"
