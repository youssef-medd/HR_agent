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


def postgres_saver(conn_str: str) -> object:
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver.from_conn_string(conn_str)
    saver.setup()
    return saver


def memory_saver() -> object:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
