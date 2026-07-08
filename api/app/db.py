"""SQLAlchemy engine + session factory.

`Base` is the declarative base every ORM model inherits from. Alembic imports it
via `migrations/env.py` for autogenerate.

`get_db` is the FastAPI dependency that yields a scoped session per request and
guarantees `close()` on exit.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
