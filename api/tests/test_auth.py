from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.user import User


def test_login_returns_jwt(client: TestClient, admin_user: User) -> None:
    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.local", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 40


def test_login_wrong_password_returns_401(client: TestClient, admin_user: User) -> None:
    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.local", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/auth/login",
        data={"username": "ghost@test.local", "password": "whatever"},
    )
    assert resp.status_code == 401


def test_me_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_token_returns_current_user(client: TestClient, admin_user: User) -> None:
    login = client.post(
        "/auth/login",
        data={"username": "admin@test.local", "password": "correct-horse-battery"},
    )
    token = login.json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@test.local"
    assert body["role"] == "admin"
