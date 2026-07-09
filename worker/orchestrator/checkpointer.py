"""LangGraph checkpointer factory.

Production: `PostgresSaver` backed by a `psycopg` connection pool. Same
database as Alembic, but LangGraph provisions its own `checkpoints*` tables
via `.setup()` on first boot — those are intentionally not managed by Alembic
(see ADR-014).

`DATABASE_URL` in `.env` follows the SQLAlchemy convention
`postgresql+psycopg://…`. The `+psycopg` driver hint is stripped here because
raw psycopg does not accept it.

Tests: `MemorySaver` — pure in-process, zero infra. The AC #1 test uses this
and asserts the ledger + resume behaviour is independent of the storage
backend.
"""

from __future__ import annotations


def _to_psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def postgres_saver(conn_str: str) -> object:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=_to_psycopg_url(conn_str),
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    # Keep a reference on the saver so the pool is not garbage-collected
    # while the worker is running.
    saver._pool = pool  # type: ignore[attr-defined]
    return saver


def memory_saver() -> object:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
