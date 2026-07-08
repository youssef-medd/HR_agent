"""Smoke-test chat endpoint.

Not part of the product surface. Exists so the sprint 0-1 acceptance test
(authenticate → issue one LLM call → see the trace in Langfuse) can be run over
HTTP rather than `docker exec` into the container.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.gateway import llm_call
from app.models.user import User
from app.security import require_role

router = APIRouter(prefix="/chat", tags=["chat"])


class HelloRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class HelloResponse(BaseModel):
    reply: str


@router.post("/hello", response_model=HelloResponse)
def hello(
    body: HelloRequest,
    user: Annotated[User, Depends(require_role("admin", "recruiter"))],
) -> HelloResponse:
    reply = llm_call(
        profile="chat",
        messages=[
            {"role": "system", "content": "You are a concise assistant. Answer in one short sentence."},
            {"role": "user", "content": body.prompt},
        ],
        user_id=str(user.id),
        metadata={"endpoint": "/chat/hello", "role": user.role},
    )
    return HelloResponse(reply=reply)
