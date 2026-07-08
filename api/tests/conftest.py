"""Pytest fixtures.

Runs the app against an in-memory SQLite so the test suite has no Postgres
dependency. Env vars are stamped before any `app.*` import so
`pydantic-settings` and the module-level engine pick them up.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-do-not-use-in-prod-" + "x" * 32)
os.environ.setdefault("JWT_EXPIRE_HOURS", "1")
os.environ.setdefault("GROQ_API_KEY", "stub-not-called-in-unit-tests")
os.environ.setdefault("MODEL_EXTRACT", "stub")
os.environ.setdefault("MODEL_JUDGE", "stub")
os.environ.setdefault("MODEL_CHAT", "stub")
os.environ.setdefault("ADMIN_EMAIL", "test-admin@welyne.local")
os.environ.setdefault("ADMIN_PASSWORD", "unit-test-password-12345")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import hash_password  # noqa: E402

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False, future=True)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.create_all(_test_engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(_test_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_user() -> User:
    with _TestSession() as db:
        user = User(
            email="admin@test.local",
            password_hash=hash_password("correct-horse-battery"),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
