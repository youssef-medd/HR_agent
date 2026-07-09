"""A0 Orchestrator.

Supervisor graph that routes work between agents (A1–A9), owns the
application state machine (spec §2.1), enforces human gates, retries with
idempotency, and writes the audit trail. Lives inside the Celery worker.
"""
