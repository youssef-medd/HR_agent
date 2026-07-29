"""A3 — candidate deduplication."""

from __future__ import annotations

from app.models.candidate import Candidate

from orchestrator.dedup import dedup_candidate


def test_new_candidate_created(db):
    v = dedup_candidate(db, {"full_name": "Jane Doe", "email": "jane@x.io", "phone": "+21620000000"})
    assert v["duplicate"] is False
    assert v["candidate_id"] is not None
    assert v["matched_on"] is None
    assert db.get(Candidate, v["candidate_id"]) is not None


def test_same_email_is_duplicate(db):
    first = dedup_candidate(db, {"full_name": "Jane Doe", "email": "JANE@x.io"})
    second = dedup_candidate(db, {"full_name": "Jane D.", "email": "jane@x.io"})  # case-insensitive
    assert second["duplicate"] is True
    assert second["matched_on"] == "email"
    assert second["candidate_id"] == first["candidate_id"]


def test_same_phone_is_duplicate(db):
    first = dedup_candidate(db, {"full_name": "Bob", "phone": "+216 20 111 222"})
    second = dedup_candidate(db, {"full_name": "Bob", "phone": "+21620111222"})  # spacing ignored
    assert second["duplicate"] is True and second["matched_on"] == "phone"
    assert second["candidate_id"] == first["candidate_id"]


def test_fuzzy_name_flags_possible_not_merged(db):
    dedup_candidate(db, {"full_name": "Jonathan Smith", "email": "j1@x.io"})
    v = dedup_candidate(db, {"full_name": "Jonathan Smith", "email": "j2@x.io"})  # diff email
    assert v["duplicate"] is False  # not auto-merged
    assert v["possible_match_id"] is not None


def test_distinct_people_not_matched(db):
    dedup_candidate(db, {"full_name": "Alice Alpha", "email": "alice@x.io"})
    v = dedup_candidate(db, {"full_name": "Zoe Omega", "email": "zoe@x.io"})
    assert v["duplicate"] is False and v["possible_match_id"] is None
