"""§5.4 — scoring/bias eval harness metrics."""

from __future__ import annotations

from orchestrator.evals import (
    run_bias_probe,
    run_scoring_eval,
    spearman,
    stddev,
)


def test_spearman_perfect_and_inverse():
    assert round(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 6) == 1.0
    assert round(spearman([1, 2, 3, 4], [40, 30, 20, 10]), 6) == -1.0


def test_stddev():
    assert stddev([5, 5, 5]) == 0.0
    assert round(stddev([2, 4, 6]), 4) == round((8 / 3) ** 0.5, 4)


def _items():
    # recruiter_score higher = better; cv carries a "q" quality signal.
    return [
        {"id": f"c{i}", "jd": "", "cv": {"q": q}, "recruiter_score": q}
        for i, q in enumerate([10, 30, 50, 70, 90])
    ]


def test_run_scoring_eval_passes_when_aligned():
    # A deterministic scorer that mirrors recruiter quality -> spearman 1, stddev 0.
    report = run_scoring_eval(_items(), lambda cv, jd: cv["q"], runs=3)
    assert report["spearman"] == 1.0
    assert report["max_stddev"] == 0.0
    assert report["passed"] is True


def test_run_scoring_eval_fails_when_misaligned():
    # Scorer inversely related to recruiter ranking -> spearman -1 -> fails target.
    report = run_scoring_eval(_items(), lambda cv, jd: 100 - cv["q"], runs=1)
    assert report["spearman"] == -1.0
    assert report["passed"] is False


def test_run_scoring_eval_flags_instability():
    # Non-deterministic scorer -> stddev exceeds the target even if ranking is ok.
    seq = iter([10, 20, 30] * 5)
    report = run_scoring_eval(
        [{"id": "x", "jd": "", "cv": {}, "recruiter_score": 1}],
        lambda cv, jd: next(seq), runs=3,
    )
    assert report["max_stddev"] >= 5.0
    assert report["passed"] is False


def test_bias_probe_equal_and_unequal():
    ok = run_bias_probe(
        [{"id": "p", "jd": "", "a": {"x": 1}, "b": {"x": 1}}],
        lambda cv, jd: 50.0,
    )
    assert ok["passed"] is True

    bad = run_bias_probe(
        [{"id": "p", "jd": "", "a": {"g": "f"}, "b": {"g": "m"}}],
        lambda cv, jd: 40.0 if cv.get("g") == "f" else 60.0,  # identity leaks
    )
    assert bad["passed"] is False


# --- A3 parser eval (§5.4: names, dates, titles, skills) ----------------------

import json  # noqa: E402

from orchestrator.evals import (  # noqa: E402
    DEFAULT_PARSER_FIELDS,
    list_recall,
    run_parser_eval,
)

_PROFILE = {
    "full_name": "Omar Ben Salah",
    "email": "Omar.BenSalah@gmail.com",
    "phone": "00216 24 118 903",
    "location": "Tunis, Tunisia",
    "skills": ["Python", "Go", "PostgreSQL", "Docker"],
    "languages": ["Arabic", "French", "English"],
    "certifications": ["AWS Certified Solutions Architect"],
    "years_experience": 8.5,
    "experiences": [
        {"title": "Senior Backend Engineer", "company": "Paymee", "start": "2021-03", "end": "present"},
        {"title": "Backend Engineer", "company": "Instadeep", "start": "2018-01", "end": "2021-02"},
    ],
    "education": [{"institution": "ENSI Manouba", "degree": "Engineering", "year": "2017"}],
}

_EXPECTED = {
    "full_name": "OMAR BEN SALAH",
    "email": "omar.bensalah@gmail.com",
    "phone": "+216 24 118 903",
    "location": "Tunis",
    "title": "Senior Backend Engineer",
    "current_employer": "Paymee",
    "employers": ["Paymee", "Instadeep"],
    "education": ["ENSI"],
    "skills": ["Python", "Go", "PostgreSQL"],
    "languages": ["Arabic", "French", "English"],
    "certifications": ["AWS Certified Solutions Architect"],
    "years_experience": 8,
}


def _corpus(tmp_path, expected, files=("cv.pdf",)):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": [{"file": f, "expected": expected} for f in files]}),
        encoding="utf-8",
    )
    for f in files:
        (tmp_path / f).write_bytes(b"%PDF-")
    return tmp_path


def test_parser_eval_scores_every_spec_field(tmp_path):
    report = run_parser_eval(
        lambda name, data: _PROFILE, cv_dir=_corpus(tmp_path, _EXPECTED)
    )
    assert report["parse_success"] == 1.0
    # Every default field except `dates` has a manifest key here; `dates` is
    # structural and always checked.
    assert set(report["fields"]) == set(DEFAULT_PARSER_FIELDS)
    assert report["field_accuracy"] == 1.0
    assert report["passed"] is True
    assert report["per_file"][0]["checks"]["title"] is True


def test_parser_eval_catches_wrong_title_and_missing_skills(tmp_path):
    bad = {
        **_PROFILE,
        "skills": ["Excel"],
        "experiences": [{"title": "Chef", "company": "Paymee", "start": "2021", "end": "present"}],
    }
    report = run_parser_eval(lambda name, data: bad, cv_dir=_corpus(tmp_path, _EXPECTED))
    checks = report["per_file"][0]["checks"]
    assert checks["title"] is False
    assert checks["skills"] is False
    assert checks["current_employer"] is True  # still the right employer
    assert report["by_field"]["skills"]["accuracy"] == 0.0
    assert report["passed"] is False


def test_parser_eval_flags_broken_timeline(tmp_path):
    # An experience with no start year, and one ending before it starts.
    broken = {
        **_PROFILE,
        "experiences": [
            {"title": "Senior Backend Engineer", "company": "Paymee", "start": "", "end": "present"},
        ],
    }
    report = run_parser_eval(lambda name, data: broken, cv_dir=_corpus(tmp_path, _EXPECTED))
    assert report["per_file"][0]["checks"]["dates"] is False

    reversed_dates = {
        **_PROFILE,
        "experiences": [{"title": "X", "company": "Paymee", "start": "2021", "end": "2019"}],
    }
    report = run_parser_eval(
        lambda name, data: reversed_dates, cv_dir=_corpus(tmp_path, _EXPECTED)
    )
    assert report["per_file"][0]["checks"]["dates"] is False


def test_parser_eval_records_parse_failures(tmp_path):
    def _boom(name, data):
        raise ValueError("no text layer")

    report = run_parser_eval(_boom, cv_dir=_corpus(tmp_path, _EXPECTED))
    assert report["parsed"] == 0 and report["parse_success"] == 0.0
    assert "no text layer" in report["per_file"][0]["error"]
    assert report["passed"] is False


def test_list_recall_is_accent_and_substring_tolerant():
    assert list_recall(["ENSI"], ["ENSI Manouba"]) == 1.0
    assert list_recall(["Ingénierie"], ["ingenierie logicielle"]) == 1.0
    assert list_recall(["Python", "Go", "Rust"], ["Python", "Go"]) == 2 / 3
    assert list_recall([], ["anything"]) == 1.0  # nothing claimed, nothing to miss


def test_parser_eval_field_subset(tmp_path):
    report = run_parser_eval(
        lambda name, data: _PROFILE,
        cv_dir=_corpus(tmp_path, _EXPECTED),
        fields=("full_name", "skills"),
    )
    assert report["fields"] == ["full_name", "skills"]
    assert report["fields_checked"] == 2


# --- A5 scripted-dialogue eval ------------------------------------------------

from orchestrator.agents.prescreen import (  # noqa: E402
    AnswerInterpretation,
    ConsentInterpretation,
    SlotCoverage,
)
from orchestrator.evals import run_dialogue, run_dialogue_eval  # noqa: E402


def _fns(*, consent=True, sensitive_on=None, answered_on=None, covers=None):
    def consent_fn(t):
        return ConsentInterpretation(consent=consent)

    def answer_fn(q, r):
        if sensitive_on and sensitive_on in r:
            return AnswerInterpretation(answer=r, answered=True, sensitive=True)
        if answered_on is not None and answered_on in r:
            return AnswerInterpretation(answer="", answered=False)
        return AnswerInterpretation(answer=r, answered=True)

    def coverage_fn(q, prior):
        if covers and covers in q:
            return SlotCoverage(covered=True, answer="from earlier")
        return SlotCoverage()

    return consent_fn, answer_fn, coverage_fn


def test_run_dialogue_complete():
    c, a, cov = _fns()
    out = run_dialogue(
        {"id": "d", "questions": ["Q1", "Q2"], "consent_reply": "yes", "replies": ["a1", "a2"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert out["outcome"] == "complete"
    assert [x["a"] for x in out["answers"]] == ["a1", "a2"]


def test_run_dialogue_no_consent_stops_before_questions():
    c, a, cov = _fns(consent=False)
    out = run_dialogue(
        {"id": "d", "questions": ["Q1"], "consent_reply": "no", "replies": ["a1"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert out["outcome"] == "no_consent" and out["answers"] == []


def test_run_dialogue_sensitive_hands_off():
    c, a, cov = _fns(sensitive_on="lawyer")
    out = run_dialogue(
        {"id": "d", "questions": ["Q1", "Q2"], "consent_reply": "yes", "replies": ["my lawyer said no"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert out["outcome"] == "handoff"


def test_run_dialogue_reasks_once_then_gives_up():
    c, a, cov = _fns(answered_on="hmm")
    ok = run_dialogue(
        {"id": "d", "questions": ["Q1"], "consent_reply": "yes", "replies": ["hmm", "6 years"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert ok["outcome"] == "complete"  # recovered on the single re-ask

    bad = run_dialogue(
        {"id": "d", "questions": ["Q1"], "consent_reply": "yes", "replies": ["hmm", "hmm"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert bad["outcome"] == "unclear"  # never argues past one re-ask


def test_run_dialogue_skips_covered_slot():
    """One reply covering two slots must not need a second reply."""
    c, a, cov = _fns(covers="Notice")
    out = run_dialogue(
        {"id": "d", "questions": ["Experience?", "Notice period?"], "consent_reply": "yes",
         "replies": ["6 years, can start in a month"]},
        consent_fn=c, answer_fn=a, coverage_fn=cov,
    )
    assert out["outcome"] == "complete"
    assert out["asked"] == 1  # only one question actually asked
    assert out["answers"][1]["auto"] is True


def test_dialogue_eval_scores_against_target():
    c, a, cov = _fns()
    dialogues = [
        {"id": f"d{i}", "lang": "en", "expect": "complete", "questions": ["Q1"],
         "consent_reply": "yes", "replies": ["a1"]}
        for i in range(4)
    ]
    # one that legitimately cannot complete (no reply available)
    dialogues.append({"id": "short", "lang": "fr", "expect": "complete", "questions": ["Q1"],
                      "consent_reply": "yes", "replies": []})
    report = run_dialogue_eval(dialogues, consent_fn=c, answer_fn=a, coverage_fn=cov)

    assert report["n"] == 5 and report["completed"] == 4
    assert report["completion_rate"] == 0.8
    assert report["passed"] is True  # exactly at the 80% target
    assert report["by_language"]["en"]["complete"] == 4
