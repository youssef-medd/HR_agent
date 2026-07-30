"""§7 — sensitive decisions write an immutable audit row."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.needs_attention import NeedsAttention

from orchestrator import side_effects
from orchestrator.gates import execute_after_offer_gate, execute_after_rejection_gate


@pytest.fixture(autouse=True)
def _stub_transports(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASS", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MODEL_JUDGE", "test-judge-model")
    side_effects._sent_log_reset()


def _approved_gate(db, gate: str, *, ref="c@x.io") -> int:
    row = Application(job_id=1, candidate_ref=ref, state="INTERVIEWED", payload={})
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(NeedsAttention(
        application_id=row.id, reason="sensitive_gate", gate=gate, status="closed",
        resolved_by="recruiter@welyne.local", resolution={"decision": "approve"},
        resolved_at=datetime.now(UTC),
    ))
    db.commit()
    return row.id


def test_offer_gate_writes_audit(db):
    app_id = _approved_gate(db, "offer")
    execute_after_offer_gate(db, app_id, "c@x.io", "offer@v1")

    log = db.query(AuditLog).filter_by(subject_id=str(app_id), action="offer_sent").one()
    assert log.actor == "recruiter@welyne.local"
    assert log.model == "test-judge-model"
    assert log.prompt_version  # score prompt version recorded
    assert log.subject_type == "application"


def test_rejection_gate_writes_audit(db):
    app_id = _approved_gate(db, "rejection")
    execute_after_rejection_gate(db, app_id, "c@x.io", "rejection@v1")

    log = db.query(AuditLog).filter_by(subject_id=str(app_id), action="rejection_sent").one()
    assert log.actor == "recruiter@welyne.local"
    assert log.payload["template"] == "rejection@v1"
