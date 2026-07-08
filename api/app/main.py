"""FastAPI app entry point.

Kept intentionally thin: wire routers, expose `/health`, and let uvicorn
discover the `app` symbol via `app.main:app`.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import auth, chat

app = FastAPI(title="Welyne HR AI Agent", version="0.1.0")

app.include_router(auth.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
