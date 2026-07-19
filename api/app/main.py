"""FastAPI app entry point.

Kept intentionally thin: wire routers, expose `/health`, and let uvicorn
discover the `app` symbol via `app.main:app`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import applications, attention, auth, chat, jobs, public, reports, whatsapp

app = FastAPI(title="Welyne HR AI Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(applications.router)
app.include_router(attention.router)
app.include_router(jobs.router)
app.include_router(public.router)
app.include_router(reports.router)
app.include_router(whatsapp.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
