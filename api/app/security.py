"""Auth primitives.

Hashing (bcrypt directly — passlib is unmaintained and breaks against bcrypt
>=4.1), JWT issuance/verification, and the `require_role` FastAPI dependency
factory used to gate routes by role (spec §7).

bcrypt only hashes the first 72 bytes of a password. Longer inputs are
truncated explicitly so the behavior is deterministic; login uses the same
truncation so verification stays consistent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.user import User

_BCRYPT_MAX = 72
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(*, sub: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: Annotated[str, Depends(_oauth2)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    payload = _decode(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token subject")
    user = db.get(User, int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(*allowed: str):
    """FastAPI dependency factory: 403 unless user's role is in `allowed`."""

    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not allowed",
            )
        return user

    return _dep
