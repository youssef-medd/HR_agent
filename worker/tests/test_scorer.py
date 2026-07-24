"""A4 scoring tests — offline (the judge gateway is monkeypatched).

Covers the identity-blind masking (incl. the identity-swap invariance that
underpins the bias probe, ADR-005), the score_candidate gateway call, and both
score_node branches.
"""

from __future__ import annotations

import pytest

from app.models.application import Application
from orchestrator.agents import scorer as scorer_mod
from orchestrator.agents.masking import mask_cv
from orchestrator.agents.parser import CVData
from orchestrator.agents.scorer import ScoreError, ScoreResult, score_candidate


def _cv(**over) -> CVData:
    base = dict(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="+216 20 000 000",
        location="Tunis",
        summary="Backend engineer",
        skills=["Python", "SQL"],
        languages=["English"],
        years_experience=5.0,
        experiences=[{"title": "Dev", "company": "Acme", "start": "2019", "end": "2024", "summary": "APIs"}],
        education=[{"degree": "BSc CS", "institution": "INSAT", "year": "2018"}],
    )
    base.update(over)
    return CVData.model_validate(base)


def test_mask_drops_identity_fields():
    masked = mask_cv(_cv())
    flat = str(masked)
    assert "Jane Doe" not in flat
    assert "jane@example.com" not in flat
    assert "+216 20 000 000" not in flat
    assert "Tunis" not in flat
    assert "INSAT" not in flat  # institution redacted
    assert masked["skills"] == ["Python", "SQL"]  # signal kept


def test_mask_is_identity_swap_invariant():
    # Two CVs differing ONLY in identity fields must mask to the same view.
    a = mask_cv(_cv(full_name="Jane Doe", email="jane@x.com", location="Tunis"))
    b = mask_cv(_cv(full_name="John Smith", email="john@y.com", location="Berlin"))
    assert a == b


def test_mask_scrubs_freetext_contact_and_dob():
    # ADR-004: email and day-precision dates (a DOB hides here) are scrubbed from
    # free-text summaries; year-only ranges survive.
    masked = mask_cv(
        _cv(
            summary="Reach me at jane@x.com. Born 12/05/1994. Active 2019-2024.",
            experiences=[{"title": "Dev", "company": "Acme", "start": "2019", "end": "2024",
                          "summary": "Contact bob@y.io"}],
        )
    )
    assert "jane@x.com" not in masked["summary"]
    assert "12/05/1994" not in masked["summary"]
    assert "2019-2024" in masked["summary"]  # duration preserved
    assert "bob@y.io" not in masked["experiences"][0]["summary"]


def test_score_reversed_order_rank_invariance(monkeypatch):
    # ADR-005: single-candidate scoring is order-invariant — scoring a batch
    # forward vs reversed preserves each profile's score (rank correlation 1.0).
    def fake_llm_call(*, profile, messages, schema, **_):
        content = messages[1]["content"]
        n = content.count("python")  # stable per profile, distinct across profiles
        return ScoreResult(
            overall=0, skills_match=min(100, 30 + n * 10),
            experience_match=50, education_match=50,
        )

    monkeypatch.setattr(scorer_mod, "llm_call", fake_llm_call)

    profiles = [{"skills": ["python"] * k} for k in range(1, 6)]
    forward = [score_candidate(p, "jd").overall for p in profiles]
    reversed_scores = [score_candidate(p, "jd").overall for p in reversed(profiles)]
    realigned = list(reversed(reversed_scores))

    assert forward == realigned  # identical => Spearman rank correlation = 1.0
    assert len(set(forward)) == len(forward)  # profiles genuinely distinct


def test_score_candidate_uses_judge_profile(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return ScoreResult(
            overall=1, skills_match=90, experience_match=80, education_match=60,
            recommendation="decline",
        )

    monkeypatch.setattr(scorer_mod, "llm_call", fake_llm_call)

    result = score_candidate({"skills": ["Python"]}, "Backend role", user_id="7")

    assert isinstance(result, ScoreResult)
    # overall + recommendation recomputed deterministically: .5*90+.35*80+.15*60 = 82
    assert result.overall == 82
    assert result.recommendation == "shortlist"
    assert captured["profile"] == "judge"
    assert captured["schema"] is ScoreResult
    assert captured["metadata"]["agent"] == "A4"


def test_finalize_weighted_bands():
    from orchestrator.agents.scorer import _finalize

    # pool band: .5*60+.35*50+.15*40 = 53.5 -> 54
    mid = _finalize(ScoreResult(overall=0, skills_match=60, experience_match=50, education_match=40))
    assert mid.overall == 54 and mid.recommendation == "pool"

    # decline band
    low = _finalize(ScoreResult(overall=99, skills_match=20, experience_match=10, education_match=0))
    assert low.overall == 14 and low.recommendation == "decline"


def test_score_candidate_wraps_validation_error(monkeypatch):
    def boom(**_):
        return ScoreResult.model_validate({"overall": 999})  # ge=0,le=100 -> error

    monkeypatch.setattr(scorer_mod, "llm_call", boom)
    with pytest.raises(ScoreError):
        score_candidate({"skills": []}, "jd")


def _seed(db_factory, payload: dict) -> int:
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="a@b.c", state="PARSED", payload=payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def test_score_node_stores_score_and_advances(db_factory, monkeypatch):
    from orchestrator import nodes

    monkeypatch.setattr(
        nodes,
        "score_candidate",
        lambda masked, jd, **_: ScoreResult(overall=77, recommendation="shortlist"),
    )
    app_id = _seed(db_factory, {"cv": {"full_name": "Jane", "skills": ["Python"]}, "jd_text": "Backend"})

    with db_factory() as db:
        state = nodes.score_node(db, {"application_id": app_id, "stage": "PARSED", "attempt": 1})

    assert state["stage"] == "SCORED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "SCORED"
        assert row.payload["score"]["overall"] == 77


def test_score_candidate_honours_per_job_weights(monkeypatch):
    def fake(*, profile, messages, schema, **_):
        return ScoreResult(overall=0, skills_match=90, experience_match=40, education_match=40)

    monkeypatch.setattr(scorer_mod, "llm_call", fake)

    # skills-only weighting -> overall == skills_match
    skills_only = score_candidate({}, "jd", weights={"skills": 100, "experience": 0, "education": 0})
    assert skills_only.overall == 90 and skills_only.recommendation == "shortlist"

    # education-only weighting -> overall == education_match
    edu_only = score_candidate({}, "jd", weights={"skills": 0, "experience": 0, "education": 100})
    assert edu_only.overall == 40 and edu_only.recommendation == "decline"


def test_check_hard_filters(monkeypatch):
    from orchestrator.agents.scorer import HardFilterCheck, check_hard_filters

    # no criteria -> no LLM call, empty result
    monkeypatch.setattr(scorer_mod, "llm_call", lambda **_: (_ for _ in ()).throw(AssertionError()))
    assert check_hard_filters({}, []) == []

    # criteria present -> returns the unmet subset
    monkeypatch.setattr(
        scorer_mod, "llm_call", lambda **_: HardFilterCheck(unmet=["Work permit"])
    )
    assert check_hard_filters({"skills": ["Python"]}, ["Work permit", "Python"]) == ["Work permit"]


def test_score_node_hard_filter_forces_decline(db_factory, monkeypatch):
    from orchestrator import nodes
    from app.models.job import Job

    with db_factory() as db:
        db.add(
            Job(
                id=1,
                title="Backend",
                status="published",
                spec={
                    "spec": {"eliminatory_criteria": ["Valid work permit"]},
                    "weights": {"skills": 60, "experience": 30, "education": 10},
                },
            )
        )
        db.commit()

    monkeypatch.setattr(nodes, "check_hard_filters", lambda masked, crit, **_: ["Valid work permit"])
    monkeypatch.setattr(
        nodes, "score_candidate",
        lambda masked, jd, **_: ScoreResult(overall=88, recommendation="shortlist"),
    )
    app_id = _seed(db_factory, {"cv": {"skills": ["Python"]}, "jd_text": "Backend"})

    with db_factory() as db:
        nodes.score_node(db, {"application_id": app_id, "stage": "PARSED", "attempt": 1})

    with db_factory() as db:
        score = db.get(Application, app_id).payload["score"]
        assert score["recommendation"] == "decline"  # hard filter overrides the judge
        assert score["hard_filter_failures"] == ["Valid work permit"]
        assert score["weights_used"] == {"skills": 60, "experience": 30, "education": 10}


def test_score_node_routes_to_needs_attention_on_error(db_factory, monkeypatch):
    from orchestrator import nodes

    def boom(masked, jd, **_):
        raise ScoreError("judge broke")

    monkeypatch.setattr(nodes, "score_candidate", boom)
    app_id = _seed(db_factory, {"cv": {"skills": ["Python"]}})

    with db_factory() as db:
        state = nodes.score_node(db, {"application_id": app_id, "stage": "PARSED", "attempt": 1})

    assert state["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        assert db.get(Application, app_id).state == "NEEDS_ATTENTION"
