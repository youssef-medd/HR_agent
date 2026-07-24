"""WhatsApp Cloud API webhook.

Two endpoints Meta calls:

- `GET /webhooks/whatsapp` — the one-time verification handshake. Meta sends
  `hub.verify_token`; we echo `hub.challenge` back only when the token matches
  `WHATSAPP_VERIFY_TOKEN`.
- `POST /webhooks/whatsapp` — inbound messages. A candidate's reply is matched
  to the application currently awaiting one (state PRESCREENING for A5, or
  PRESCREENED for A6) by phone number, then handed to the orchestrator exactly
  like the stub reply endpoints do — `enqueue_application_step(id,
  {"candidate_message": text})`. Always returns 200 so Meta does not retry.

Optional payload authenticity: when `WHATSAPP_APP_SECRET` is set, the
`X-Hub-Signature-256` header is verified (HMAC-SHA256 of the raw body).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.application import Application
from app.queue import enqueue_application_step

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])

# States in which an application is paused waiting on a candidate WhatsApp reply.
_AWAITING_STATES = ("PRESCREENING", "PRESCREENED")


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


@router.get("")
def verify(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta verification handshake. Echoes the challenge on a token match."""
    if (
        mode == "subscribe"
        and settings.whatsapp_verify_token
        and token == settings.whatsapp_verify_token
    ):
        return Response(content=challenge or "", media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


def _signature_ok(raw: bytes, header: str | None) -> bool:
    secret = settings.whatsapp_app_secret
    if not secret:
        return True  # signature enforcement disabled
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def _find_application(db: Session, from_phone: str) -> Application | None:
    """Match an inbound sender phone to a paused application.

    Compares the sender digits against each waiting application's
    `candidate_ref` and parsed CV phone, suffix-tolerant (Meta omits the '+').
    """
    want = _digits(from_phone)
    if not want:
        return None
    rows = db.scalars(
        select(Application)
        .where(Application.state.in_(_AWAITING_STATES))
        .order_by(Application.id.desc())
    ).all()
    for row in rows:
        candidates = [
            row.payload.get("phone"),
            (row.payload.get("cv") or {}).get("phone"),
            row.candidate_ref,
        ]
        for cand in candidates:
            d = _digits(cand)
            if d and (d == want or d.endswith(want) or want.endswith(d)):
                return row
    return None


def _iter_text_messages(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten a webhook payload into (from_phone, text) pairs."""
    out: list[tuple[str, str]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                if msg.get("type") == "text":
                    body = (msg.get("text") or {}).get("body")
                    sender = msg.get("from")
                    if body and sender:
                        out.append((sender, body))
    return out


@router.post("")
async def receive(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Inbound messages. Resumes the paused orchestrator thread per message."""
    raw = await request.body()
    if not _signature_ok(raw, x_hub_signature_256):
        return {"status": "ignored"}

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return {"status": "ignored"}

    delivered = 0
    for from_phone, text in _iter_text_messages(payload):
        app_row = _find_application(db, from_phone)
        if app_row is not None:
            enqueue_application_step(app_row.id, {"candidate_message": text})
            delivered += 1

    return {"status": "ok", "delivered": str(delivered)}
