"""Seed the initial admin user.

Idempotent: skips if a user with `ADMIN_EMAIL` already exists.

    docker exec welyne-api python -m scripts.seed_admin
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.user import User
from app.security import hash_password


def main() -> int:
    if not settings.admin_password:
        print("ADMIN_PASSWORD is empty — refusing to seed a passwordless admin.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == settings.admin_email))
        if existing is not None:
            print(f"Admin {settings.admin_email} already exists (id={existing.id}). No-op.")
            return 0

        user = User(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Admin seeded: id={user.id} email={user.email}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
