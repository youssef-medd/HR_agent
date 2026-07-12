"""Celery tasks.

`run_application_step` is the sole entry point for A0 execution. It resumes
the LangGraph thread keyed by `application_id` and feeds it the event that
triggered this invocation (application created, parsing done, score ready,
recruiter action). Retries are backed off; on final failure a
`NeedsAttention` row is written with reason `retry_exhausted`.
"""

from __future__ import annotations

from typing import Any

from celery.utils.log import get_task_logger
from langgraph.types import Command
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.application import Application
from app.models.needs_attention import NeedsAttention
from orchestrator.celery_app import celery
from orchestrator.checkpointer import postgres_saver
from orchestrator.config import settings
from orchestrator.graph import build_graph

logger = get_task_logger(__name__)

_engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
_SessionLocal = sessionmaker(
    bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
)


def _db_factory():
    return _SessionLocal()


_saver = None
_graph = None


def _get_graph():
    global _saver, _graph
    if _graph is None:
        _saver = postgres_saver(settings.database_url)
        _graph = build_graph(_db_factory, _saver)
    return _graph


@celery.task(bind=True, name="orchestrator.run_application_step", max_retries=3)
def run_application_step(self, application_id: int, event: dict[str, Any]) -> dict[str, Any]:
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": str(application_id)}}

        snapshot = graph.get_state(config)
        if snapshot.next:
            # Thread is paused at a human gate (interrupt). Resume it with the
            # recruiter decision carried in `event` rather than restarting from
            # START — a fresh input dict would re-run every completed node and
            # open a second gate.
            result = graph.invoke(Command(resume=event), config=config)
        elif snapshot.created_at is not None:
            # Thread already ran to a terminal state. Re-invocation is a no-op;
            # do not restart it (node bodies that write rows outside the
            # idempotency ledger — gate creation, audit events — would duplicate).
            return {
                "application_id": application_id,
                "final_stage": snapshot.values.get("stage"),
            }
        else:
            # Fresh thread — start from the beginning.
            initial_state = {"application_id": application_id, "stage": "RECEIVED", "attempt": 1}
            result = graph.invoke({**initial_state, **event}, config=config)

        return {"application_id": application_id, "final_stage": result.get("stage")}
    except Exception as exc:
        logger.exception("Step failed for application %s", application_id)
        try:
            self.retry(exc=exc, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            with _db_factory() as db:
                app_row = db.get(Application, application_id)
                if app_row is not None:
                    app_row.state = "NEEDS_ATTENTION"
                db.add(
                    NeedsAttention(
                        application_id=application_id,
                        reason="retry_exhausted",
                        context={"error": str(exc), "event": event},
                    )
                )
                db.commit()
            raise
        raise
