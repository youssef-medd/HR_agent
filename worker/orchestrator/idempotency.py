"""Idempotency ledger helper.

`with_ledger` wraps every side-effecting step in the orchestrator. Replays hit
the ledger first: if a previous attempt already succeeded, the recorded
result is returned and the effect is skipped. This is what turns "kill the
worker mid-batch, restart, zero duplicates" into a testable property.

Row lifecycle:

    pending  ── success ──►  success   (result cached)
       │
       └── crash ─►  status stays pending until retry increments `attempt`.

Concurrent writers on the same key hit the unique constraint and one loses;
the loser raises `ConcurrentAttempt`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_ledger import IdempotencyLedger


class ConcurrentAttempt(RuntimeError):
    pass


def with_ledger(
    db: Session,
    application_id: int,
    step: str,
    attempt: int,
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    row = db.scalar(
        select(IdempotencyLedger).where(
            IdempotencyLedger.application_id == application_id,
            IdempotencyLedger.step == step,
            IdempotencyLedger.attempt == attempt,
        )
    )

    if row is not None and row.status == "success":
        return row.result or {}
    if row is not None and row.status == "pending":
        raise ConcurrentAttempt(
            f"Step '{step}' attempt {attempt} for application {application_id} already pending"
        )

    if row is None:
        row = IdempotencyLedger(
            application_id=application_id,
            step=step,
            attempt=attempt,
            status="pending",
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ConcurrentAttempt(
                f"Step '{step}' attempt {attempt} for application {application_id} raced"
            ) from exc

    result = fn()

    row.status = "success"
    row.result = result
    db.commit()
    return result
