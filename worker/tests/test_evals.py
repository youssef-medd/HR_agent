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
