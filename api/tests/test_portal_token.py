"""Signed portal-token tests (spec §7).

The token replaces `email + application_id` as the candidate's credential. The
id is sequential, so the old pair let anyone who knew a candidate's address walk
1, 2, 3… until they reached that person's transcript.
"""

from __future__ import annotations

import time

import pytest

from app.portal_token import (
    PortalTokenError,
    make_portal_token,
    read_portal_token,
)


def test_token_round_trips(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    token = make_portal_token(42, "Jane@Example.COM")
    # Email is normalised at mint time so verification is case-insensitive.
    assert read_portal_token(token) == (42, "jane@example.com")


def test_token_does_not_expose_the_application_id(monkeypatch):
    """The whole point: the id must not be readable from the URL."""
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    assert "42" not in make_portal_token(42, "a@b.io").split(".")[1]


def test_tampered_payload_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    body, signature = make_portal_token(42, "a@b.io").split(".", 1)
    # Re-sign nothing — swap the payload for another application's and keep the
    # old signature. This is the attack the HMAC exists to stop.
    other_body = make_portal_token(43, "a@b.io").split(".", 1)[0]
    with pytest.raises(PortalTokenError):
        read_portal_token(f"{other_body}.{signature}")


def test_token_from_a_different_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret-one")
    token = make_portal_token(42, "a@b.io")
    monkeypatch.setenv("JWT_SECRET", "secret-two")
    with pytest.raises(PortalTokenError):
        read_portal_token(token)


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    token = make_portal_token(42, "a@b.io", ttl_seconds=-1)
    assert time.time() > 0
    with pytest.raises(PortalTokenError):
        read_portal_token(token)


@pytest.mark.parametrize("bad", ["", "garbage", "a.b", "onlyonepart"])
def test_malformed_tokens_are_rejected(monkeypatch, bad):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret")
    with pytest.raises(PortalTokenError):
        read_portal_token(bad)


def test_request_link_does_not_reveal_whether_an_email_exists(client, monkeypatch):
    """A different answer for a known vs unknown address would turn the endpoint
    into an oracle for "has this person applied here"."""
    sent: list[tuple[str, list[dict[str, str]]]] = []
    monkeypatch.setattr(
        "app.routers.public.enqueue_portal_link",
        lambda email, links: sent.append((email, links)),
    )

    unknown = client.post(
        "/public/portal/request-link", json={"email": "nobody@nowhere.test"}
    )
    assert unknown.status_code == 200
    assert unknown.json() == {"sent": True}
    assert sent == []  # nothing queued for an address with no application
