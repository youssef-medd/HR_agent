"""ORM models.

Import every model here so that `Base.metadata` sees them when Alembic runs
autogenerate and when tests spin up a schema.
"""

from __future__ import annotations

from app.models.user import User

__all__ = ["User"]
