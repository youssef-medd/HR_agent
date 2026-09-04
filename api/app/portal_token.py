"""Signed candidate-portal access tokens (spec §7).

The portal used to be gated by `email` + the raw `application_id`. Two problems:
the id is sequential, so knowing a candidate's email lets you walk 1, 2, 3…
until you hit their application; and candidates had to keep a reference number
to get back in.

A token replaces both halves. It carries the application id and the email it was
issued for, signed with `JWT_SECRET`, and expires. Unguessable, and nothing for
the candidate to remember — the link in their inbox *is* the credential, the
same shape as a password-reset link.

Lives in `app.*` rather than the worker because both sides need it: the API
verifies tokens, and the worker mints them when it emails a candidate (it
imports the `app` package from the shared mount).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

# 7 days: long enough that a candidate coming back to an emailed link mid-process
# still gets in, short enough that a forwarded or leaked mail stops working.
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60


class PortalTokenError(RuntimeError):
    """Raised when a token is malformed, tampered with, or expired."""


def _secret() -> bytes:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise PortalTokenError("JWT_SECRET is not configured")
    return secret.encode("utf-8")


def _b64e(raw: bytes) -> str:
    """URL-safe base64 without padding — keeps the token clean in a query string."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    return _b64e(hmac.new(_secret(), payload, hashlib.sha256).digest())


def make_portal_token(
    application_id: int, email: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> str:
    """Mint a portal token for one application, addressed to one email."""
    body = json.dumps(
        {
            "a": int(application_id),
            # Normalised so verification is not defeated by casing or whitespace.
            "e": email.strip().lower(),
            "x": int(time.time()) + ttl_seconds,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{_b64e(body)}.{_sign(body)}"


def read_portal_token(token: str) -> tuple[int, str]:
    """Verify a token and return `(application_id, email)`.

    Raises `PortalTokenError` on anything suspect. The signature is compared
    with `hmac.compare_digest` so a wrong token cannot be discovered a byte at a
    time by timing the response.
    """
    try:
        encoded, signature = token.split(".", 1)
        body = _b64d(encoded)
    except (ValueError, TypeError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise PortalTokenError("Malformed portal token") from exc

    if not hmac.compare_digest(signature, _sign(body)):
        raise PortalTokenError("Portal token signature does not match")

    try:
        data = json.loads(body)
        application_id = int(data["a"])
        email = str(data["e"])
        expires_at = int(data["x"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PortalTokenError("Portal token payload is not readable") from exc

    if time.time() > expires_at:
        raise PortalTokenError("Portal token has expired")

    return application_id, email
