"""Celery tasks.

`run_application_step` is the sole entry point for A0 execution. It resumes
the LangGraph thread keyed by `application_id` and feeds it the event that
triggered this invocation (application created, parsing done, score ready,
recruiter action). Retries are backed off; on final failure a
`NeedsAttention` row is written with reason `retry_exhausted`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from app.interviews import due_no_shows, mark_no_show
from app.models.application import Application
from app.models.job import Job
from app.models.needs_attention import NeedsAttention
from app.rgpd import purge_expired
from celery.utils.log import get_task_logger
from langgraph.types import Command
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from orchestrator.agents.scheduler import build_ics
from orchestrator.celery_app import celery
from orchestrator.checkpointer import postgres_saver
from orchestrator.config import settings
from orchestrator.email_intake import (
    build_application,
    fetch_new_cv_attachments,
    imap_configured,
)
from orchestrator.emails import portal_link, send_email
from orchestrator.graph import build_graph
from orchestrator.idempotency import ConcurrentAttempt, with_ledger
from orchestrator.side_effects import (
    _send_interview_reminder_impl,
    _send_interview_update_impl,
    _send_prescreen_invite_impl,
    _send_whatsapp_impl,
    wa_recipient_allowed,
)

logger = get_task_logger(__name__)

_engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
_SessionLocal = sessionmaker(
    bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
)


def _db_factory():
    return _SessionLocal()


_saver = None
_graph = None


def _get_graph():
    global _saver, _graph
    if _graph is None:
        _saver = postgres_saver(settings.database_url)
        _graph = build_graph(_db_factory, _saver)
    return _graph


# Namespace for the per-application advisory lock ('WELY'), so the key cannot
# collide with a lock taken by another part of the system.
_LOCK_NAMESPACE = 0x57454C59


@contextmanager
def _application_lock(application_id: int):
    """Serialise graph steps for one application across worker processes.

    Two steps for the same application (a fast candidate reply after a slow
    one, or a beat job racing a webhook) each load the row into their own
    session; whichever commits last writes its stale `applications.state` over
    the other's, silently reverting a transition that the event log still
    shows. A Postgres session-level advisory lock makes the second step wait
    for the first instead. No-ops on a non-Postgres URL (the SQLite test DB).
    """
    if _engine.dialect.name != "postgresql":
        yield
        return

    conn = _engine.connect()
    try:
        conn.execute(
            text("SELECT pg_advisory_lock(:ns, :id)"),
            {"ns": _LOCK_NAMESPACE, "id": application_id},
        )
        conn.commit()
        yield
    finally:
        try:
            conn.execute(
                text("SELECT pg_advisory_unlock(:ns, :id)"),
                {"ns": _LOCK_NAMESPACE, "id": application_id},
            )
            conn.commit()
        finally:
            conn.close()


@celery.task(bind=True, name="orchestrator.run_application_step", max_retries=3)
def run_application_step(self, application_id: int, event: dict[str, Any]) -> dict[str, Any]:
    with _application_lock(application_id):
        return _run_application_step(self, application_id, event)


def _run_application_step(self, application_id: int, event: dict[str, Any]) -> dict[str, Any]:
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": str(application_id)}}

        # The application row is the source of truth; the checkpointer only
        # holds resumable execution state. A checkpoint that contradicts a
        # fresh DB row (e.g. after a data reset reused ids) is stale.
        with _db_factory() as db:
            app_row = db.get(Application, application_id)
            db_state = app_row.state if app_row is not None else None

        snapshot = graph.get_state(config)
        # A thread paused on `interrupt()` exposes the pending interrupt in
        # `snapshot.tasks[].interrupts` (and `snapshot.interrupts`), NOT in
        # `snapshot.next`, which is empty for an interrupt pause. Resume when
        # either signals a live thread.
        paused = bool(snapshot.next) or bool(getattr(snapshot, "interrupts", None)) or any(
            getattr(t, "interrupts", None) for t in snapshot.tasks
        )
        if paused and db_state not in ("RECEIVED", None):
            # Thread is paused at a human gate or a conversational interrupt.
            # Resume with the event (recruiter decision / candidate message)
            # rather than restarting from START.
            result = graph.invoke(Command(resume=event), config=config)
        elif snapshot.created_at is not None and db_state not in ("RECEIVED", None):
            # Thread already ran to a terminal state. Re-invocation is a no-op;
            # do not restart it (node bodies that write rows outside the
            # idempotency ledger — gate creation, audit events — would duplicate).
            return {
                "application_id": application_id,
                "final_stage": snapshot.values.get("stage"),
            }
        else:
            # Fresh application (or stale checkpoint from a reused id) — start
            # from the beginning; invoking with fresh input restarts the thread.
            if snapshot.created_at is not None:
                logger.warning(
                    "Stale checkpoint for application %s (db_state=%s) — restarting thread",
                    application_id,
                    db_state,
                )
            initial_state = {"application_id": application_id, "stage": "RECEIVED", "attempt": 1}
            result = graph.invoke({**initial_state, **event}, config=config)

        return {"application_id": application_id, "final_stage": result.get("stage")}
    except Exception as exc:
        logger.exception("Step failed for application %s", application_id)
        try:
            self.retry(exc=exc, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            with _db_factory() as db:
                app_row = db.get(Application, application_id)
                if app_row is not None:
                    app_row.state = "NEEDS_ATTENTION"
                db.add(
                    NeedsAttention(
                        application_id=application_id,
                        reason="retry_exhausted",
                        context={"error": str(exc), "event": event},
                    )
                )
                db.commit()
            raise
        raise


def _already_ingested(db, sender: str, message_id: str) -> bool:
    """True if an application from this sender already carries this message-id."""
    if not message_id:
        return False
    rows = db.scalars(
        select(Application).where(Application.candidate_ref == sender)
    ).all()
    return any((r.payload or {}).get("email_message_id") == message_id for r in rows)


@celery.task(name="orchestrator.poll_email_inbox")
def poll_email_inbox() -> dict[str, Any]:
    """A3 — pull CVs from the IMAP inbox and start each through the pipeline.

    No-op when IMAP is unconfigured. New attachments become RECEIVED
    applications (deduped by email message-id) and are handed to the
    orchestrator via the same task the upload endpoint enqueues.
    """
    if not imap_configured():
        return {"polled": 0, "created": []}

    incomings = fetch_new_cv_attachments()
    default_job_id = int(os.environ.get("INTAKE_DEFAULT_JOB_ID", "1"))
    created: list[int] = []

    with _db_factory() as db:
        job = db.get(Job, default_job_id)
        jd_text = job.description if job is not None and job.description else None

        for inc in incomings:
            if _already_ingested(db, inc.sender_email or inc.filename, inc.message_id):
                continue
            row = build_application(inc, default_job_id, jd_text)
            db.add(row)
            db.commit()
            db.refresh(row)
            run_application_step.delay(row.id, {})
            created.append(row.id)

    logger.info("Email intake: polled %d attachment(s), created %s", len(incomings), created)
    return {"polled": len(incomings), "created": created}


def _send_due_reminders(db, *, now: datetime | None = None) -> list[int]:
    """Send interview reminders for INTERVIEW_SCHEDULED apps due within 24h.

    Idempotent: an application whose `interview.reminder_sent` flag is set is
    skipped, and the flag is set on send. Testable — inject `now`.
    """
    now = now or datetime.now(UTC)
    horizon = now + timedelta(hours=24)
    rows = db.scalars(
        select(Application).where(Application.state == "INTERVIEW_SCHEDULED")
    ).all()
    reminded: list[int] = []
    for row in rows:
        interview = (row.payload or {}).get("interview") or {}
        scheduled_raw = interview.get("scheduled_at")
        if not scheduled_raw or interview.get("reminder_sent"):
            continue
        try:
            scheduled = datetime.fromisoformat(scheduled_raw)
        except ValueError:
            continue
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        if not (now <= scheduled <= horizon):
            continue
        recipient = row.candidate_ref
        when = interview.get("when") or scheduled.strftime("%a %d %b, %H:%M UTC")
        _send_interview_reminder_impl(db, row.id, recipient, when)
        interview = {**interview, "reminder_sent": True}
        row.payload = {**(row.payload or {}), "interview": interview}
        db.commit()
        reminded.append(row.id)
    return reminded


def _prescreen_last_activity(row: Application) -> datetime:
    """Best proxy for the last candidate turn: the row's updated_at (bumped only
    when a turn is processed while the graph is otherwise paused)."""
    ts = row.updated_at
    if ts is None:
        return datetime.now(UTC)
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _process_stale_prescreens(db, *, now: datetime | None = None) -> dict[str, list[int]]:
    """A5 timeout policy: after TIMEOUT_HOURS idle send one reminder; after a
    further TIMEOUT_HOURS with no reply, mark PRESCREEN_INCOMPLETE for the
    recruiter to decide. Testable — inject `now`."""
    now = now or datetime.now(UTC)
    hours = float(os.environ.get("PRESCREEN_TIMEOUT_HOURS", "48"))
    reminded: list[int] = []
    incomplete: list[int] = []
    rows = db.scalars(select(Application).where(Application.state == "PRESCREENING")).all()
    for row in rows:
        idle_h = (now - _prescreen_last_activity(row)).total_seconds() / 3600.0
        if idle_h < hours:
            continue
        block = dict((row.payload or {}).get("prescreen") or {})
        phone = (row.payload or {}).get("phone") or (row.payload or {}).get("cv", {}).get("phone")

        if not block.get("reminder_at"):
            # Same channel rule as `nodes._prescreen_channel`: a number WhatsApp
            # cannot deliver to falls back to the emailed portal link.
            if phone and wa_recipient_allowed(phone):
                _send_whatsapp_impl(
                    db, row.id, phone,
                    "Just a reminder to finish your quick pre-screening — reply here to continue.",
                )
            elif "@" in (row.candidate_ref or ""):
                _send_prescreen_invite_impl(
                    db, row.id, row.candidate_ref, portal_link(row.candidate_ref, row.id)
                )
            block["reminder_at"] = now.isoformat()
            row.payload = {**(row.payload or {}), "prescreen": block}
            db.commit()
            reminded.append(row.id)
            continue

        # Reminder already sent — is the extra grace window also elapsed?
        try:
            reminded_at = datetime.fromisoformat(block["reminder_at"])
        except (ValueError, TypeError):
            reminded_at = _prescreen_last_activity(row)
        if reminded_at.tzinfo is None:
            reminded_at = reminded_at.replace(tzinfo=UTC)
        if (now - reminded_at).total_seconds() / 3600.0 < hours:
            continue

        block["status"] = "incomplete"
        row.payload = {**(row.payload or {}), "prescreen": block}
        row.state = "NEEDS_ATTENTION"
        db.add(NeedsAttention(
            application_id=row.id, reason="prescreen_incomplete",
            context={"idle_hours": round(idle_h, 1)},
        ))
        db.commit()
        incomplete.append(row.id)
    return {"reminded": reminded, "incomplete": incomplete}


@celery.task(name="orchestrator.process_stale_prescreens")
def process_stale_prescreens() -> dict[str, Any]:
    """A5 — beat job: nudge idle pre-screens, then mark them incomplete."""
    with _db_factory() as db:
        result = _process_stale_prescreens(db)
    if result["reminded"] or result["incomplete"]:
        logger.info("Stale pre-screens: reminded %s, incomplete %s",
                    result["reminded"], result["incomplete"])
    return result


@celery.task(name="orchestrator.send_interview_reminders")
def send_interview_reminders() -> dict[str, Any]:
    """A6 — beat job: remind candidates 24h before their interview."""
    with _db_factory() as db:
        reminded = _send_due_reminders(db)
    if reminded:
        logger.info("Interview reminders sent for %s", reminded)
    return {"reminded": reminded}


def _interview_update(db, application_id: int, kind: str) -> dict[str, Any] | None:
    """Send one A6 interview update. Returns the send record, or None if skipped.

    The DB write happened in the API (`app.interviews`); this only renders and
    delivers. Reschedule/cancel carry an ICS reusing the interview's UID with the
    block's bumped `sequence`, so the candidate's calendar moves (or drops) the
    existing event instead of gaining a duplicate.
    """
    row = db.get(Application, application_id)
    if row is None:
        return None
    block = (row.payload or {}).get("interview") or {}
    scheduled_raw = block.get("scheduled_at")
    if not scheduled_raw:
        return None
    try:
        start = datetime.fromisoformat(str(scheduled_raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)

    sequence = int(block.get("sequence") or 0)
    ics = None
    if kind in ("reschedule", "cancel"):
        ics = build_ics(
            start_utc=start,
            summary="Interview",
            uid=f"welyne-interview-{application_id}",
            description=f"Interview for application {application_id}.",
            sequence=sequence,
            method="CANCEL" if kind == "cancel" else "REQUEST",
            organizer=os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or None,
            attendee=row.candidate_ref if "@" in (row.candidate_ref or "") else None,
        )

    previous_when = None
    previous_raw = block.get("previous_scheduled_at")
    if kind == "reschedule" and previous_raw:
        try:
            previous = datetime.fromisoformat(str(previous_raw).replace("Z", "+00:00"))
            previous_when = previous.strftime("%a %d %b %Y, %H:%M UTC")
        except ValueError:
            previous_when = None

    recipient = (row.payload or {}).get("phone") or row.candidate_ref
    when = block.get("when") or start.strftime("%a %d %b %Y, %H:%M UTC")
    # Exactly-once per (kind, sequence): a retried task or a duplicated broker
    # delivery must not send the invite twice.
    return with_ledger(
        db, application_id, f"interview_{kind}", sequence + 1,
        lambda: _send_interview_update_impl(
            db, application_id, recipient, kind, when,
            previous_when=previous_when, link=block.get("link") or "", ics=ics,
        ),
    )


@celery.task(name="orchestrator.send_interview_update")
def send_interview_update(application_id: int, kind: str) -> dict[str, Any]:
    """A6 — deliver a reschedule / cancellation / no-show notice to the candidate."""
    with _db_factory() as db:
        try:
            sent = _interview_update(db, application_id, kind)
        except ConcurrentAttempt:
            return {"application_id": application_id, "kind": kind, "sent": False}
        db.commit()
    return {"application_id": application_id, "kind": kind, "sent": bool(sent)}


@celery.task(name="orchestrator.detect_no_shows")
def detect_no_shows() -> dict[str, Any]:
    """A6 — beat job: flag interviews whose slot elapsed with no recorded outcome.

    The application stays INTERVIEW_SCHEDULED (the graph is parked on the offer
    gate); the miss surfaces as an open `interview_no_show` attention item for
    the recruiter, plus one rebooking nudge to the candidate.
    """
    flagged: list[int] = []
    with _db_factory() as db:
        for row in due_no_shows(db):
            mark_no_show(db, row, source="beat")
            flagged.append(row.id)
    if flagged:
        logger.info("Interview no-shows flagged for %s", flagged)
    return {"no_shows": flagged}


@celery.task(name="orchestrator.purge_expired_applications")
def purge_expired_applications() -> dict[str, Any]:
    """RGPD §7 — beat job: anonymise applications past the retention limit."""
    months = int(os.environ.get("RETENTION_MONTHS", "12"))
    with _db_factory() as db:
        purged = purge_expired(db, months=months)
    if purged:
        logger.info("Retention: anonymised %d expired application(s): %s", len(purged), purged)
    return {"purged": purged}


def _process_onboarding_docs(db, *, now: datetime | None = None) -> dict[str, list[int]]:
    """A8 — chase document collection to 100%.

    Pending document tasks past their due date get one candidate reminder; if
    still outstanding after an escalation grace window, they are marked expired
    and a NeedsAttention row escalates them to the HR manager. Testable via `now`.
    """
    from app.models.onboarding_task import OnboardingTask

    now = now or datetime.now(UTC)
    escalate_days = int(os.environ.get("ONBOARDING_ESCALATE_DAYS", "3"))
    reminded_apps: list[int] = []
    escalated: list[int] = []

    pending = db.scalars(
        select(OnboardingTask).where(
            OnboardingTask.category == "document",
            OnboardingTask.status == "pending",
        )
    ).all()

    by_app: dict[int, list] = {}
    for t in pending:
        due = t.due_at
        if due is None:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        if now >= due:
            by_app.setdefault(t.application_id, []).append((t, due))

    for app_id, items in by_app.items():
        app_row = db.get(Application, app_id)
        if app_row is None:
            continue
        # Escalate when the earliest overdue doc is past the grace window and a
        # reminder already went out.
        already_reminded = all(t.reminded_at is not None for t, _ in items)
        oldest_due = min(due for _, due in items)
        if already_reminded and now >= oldest_due + timedelta(days=escalate_days):
            for t, _ in items:
                t.status = "expired"
            db.add(NeedsAttention(
                application_id=app_id, reason="onboarding_docs_overdue",
                context={"documents": [t.label for t, _ in items]},
            ))
            db.commit()
            escalated.append(app_id)
            continue

        if not already_reminded:
            if "@" in (app_row.candidate_ref or ""):
                send_email(
                    app_row.candidate_ref,
                    "Reminder: documents needed to complete your onboarding",
                    "Hi,\n\nA few onboarding documents are still needed. Please upload them "
                    f"here:\n{portal_link(app_row.candidate_ref, app_id)}\n\nThanks!",
                )
            for t, _ in items:
                t.reminded_at = now
            db.commit()
            reminded_apps.append(app_id)

    return {"reminded": reminded_apps, "escalated": escalated}


@celery.task(name="orchestrator.process_onboarding_docs")
def process_onboarding_docs() -> dict[str, Any]:
    """A8 — beat job: remind + escalate outstanding onboarding documents."""
    with _db_factory() as db:
        result = _process_onboarding_docs(db)
    if result["reminded"] or result["escalated"]:
        logger.info("Onboarding docs: reminded %s, escalated %s",
                    result["reminded"], result["escalated"])
    return result


def _digest_body(metrics: dict[str, Any]) -> str:
    """Plain-text weekly KPI digest from an overview snapshot."""
    funnel = " → ".join(f"{f['stage']} {f['reached']}" for f in metrics.get("funnel", []))
    lines = [
        "Welyne HR — weekly recruitment digest",
        "",
        f"Applications: {metrics.get('total_applications', 0)}",
        f"Funnel: {funnel}",
        f"Shortlist rate: {metrics.get('shortlist_rate', 0):.0%}   "
        f"Hire rate: {metrics.get('hire_rate', 0):.0%}",
        f"Avg score: {metrics.get('avg_score')}",
        f"Open human-review gates: {metrics.get('open_gates', 0)}",
    ]
    return "\n".join(lines)


@celery.task(name="orchestrator.snapshot_metrics")
def snapshot_metrics() -> dict[str, Any]:
    """A9 — nightly aggregation: persist a KPI snapshot for trend charts."""
    from app.models.report_snapshot import ReportSnapshot
    from app.routers.reports import compute_overview

    with _db_factory() as db:
        metrics = compute_overview(db).model_dump()
        db.add(ReportSnapshot(metrics=metrics))
        db.commit()
    return {"snapshot": True, "total_applications": metrics.get("total_applications", 0)}


def _send_admin_digest(db) -> list[str]:
    """Email the weekly KPI digest to every admin. Returns the recipients."""
    from app.models.user import User
    from app.routers.reports import compute_overview

    admins = db.scalars(select(User).where(User.role == "admin")).all()
    recipients = [u.email for u in admins if u.email]
    if not recipients:
        return []
    body = _digest_body(compute_overview(db).model_dump())
    for email in recipients:
        send_email(email, "Welyne HR — weekly digest", body)
    return recipients


@celery.task(name="orchestrator.weekly_admin_digest")
def weekly_admin_digest() -> dict[str, Any]:
    """A9 — weekly digest email to admins."""
    with _db_factory() as db:
        recipients = _send_admin_digest(db)
    if recipients:
        logger.info("Weekly digest sent to %s", recipients)
    return {"recipients": recipients}


@celery.task(name="orchestrator.send_portal_link")
def send_portal_link(email: str, links: list[dict[str, str]]) -> dict[str, Any]:
    """Email a candidate their signed portal links (spec §7).

    The API mints the tokens — it owns `JWT_SECRET` — and hands over rendered
    title/url pairs; SMTP lives here with every other outbound message.

    Fire-and-forget by design: the endpoint answers `sent: true` regardless, so
    that a failure here cannot be timed to reveal whether the address exists.
    """
    if not email or not links:
        return {"sent": False}

    lines = ["Here are your applications with Welyne:", ""]
    for link in links:
        lines.append(f"- {link.get('title', 'Application')}")
        lines.append(f"  {link.get('url', '')}")
        lines.append("")
    lines.append("These links expire in 7 days. You can request a new one any time.")

    send_email(email, "Your Welyne application", "\n".join(lines))
    logger.info("Portal link sent to %s (%d application(s))", email, len(links))
    return {"sent": True, "count": len(links)}
