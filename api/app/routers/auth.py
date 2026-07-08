"""Auth endpoints.

`POST /auth/login` accepts OAuth2 password-form credentials so that Swagger's
"Authorize" button works out of the box. `GET /auth/me` returns the JWT-bound
user for smoke tests and future frontend session hydration.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: str
    role: str


@router.post("/login", response_model=TokenResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(sub=str(user.id), role=user.role)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, role=user.role)
