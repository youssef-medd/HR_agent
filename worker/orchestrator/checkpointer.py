"""LangGraph checkpointer factory.

Production: `PostgresSaver` bound to the app database. Same connection URL as
Alembic, but LangGraph provisions its own `checkpoints*` tables via `.setup()`
on first boot — those are intentionally not managed by Alembic (see
ADR-014).

Tests: `MemorySaver` — pure in-process, zero infra. The AC #1 test also uses
`MemorySaver` and asserts the ledger + resume behaviour is independent of the
storage backend.
"""

from __future__ import annotations

from typing import Protocol


class Saver(Protocol):
    def get(self, config: dict) -> object | None: ...


# Pins the from_conn_string() generator-contextmanagers alive for the process's
# lifetime. Without this, the only reference is the yielded PostgresSaver — the
# generator itself gets garbage-collected, which runs its `with Connection...`
# exit and silently closes the connection underneath the saver.
_open_contexts: list[object] = []


def postgres_saver(conn_str: str) -> object:
    from langgraph.checkpoint.postgres import PostgresSaver

    # PostgresSaver calls psycopg.connect() directly, which doesn't understand
    # SQLAlchemy's "+driver" dialect suffix (e.g. postgresql+psycopg://) — strip
    # it down to a plain libpq DSN.
    conn_str = conn_str.replace("postgresql+psycopg://", "postgresql://")

    # from_conn_string is a contextmanager as of langgraph-checkpoint-postgres 3.x.
    # Entered manually (never exited) since the returned saver is cached for the
    # worker process's lifetime by tasks._get_graph().
    cm = PostgresSaver.from_conn_string(conn_str)
    saver = cm.__enter__()
    _open_contexts.append(cm)
    saver.setup()
    return saver


def memory_saver() -> object:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
