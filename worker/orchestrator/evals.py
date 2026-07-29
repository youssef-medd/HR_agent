"""A4/§5.4 — scoring & bias evaluation harness.

Computes the two acceptance metrics from the spec:

- Spearman rank correlation between the platform's scores and the recruiter
  reference ranking (target >= 0.75).
- Score stability: the standard deviation across `runs` repeat scorings of the
  same CV (target < 5 points) — a determinism check.

Plus a bias probe: scores must be identical for two profiles that differ only
in identity attributes (name/gender/…), which the masking layer guarantees.

Runs against the golden set in `evals/golden/fixtures.json`. `make evals` runs
it with a deterministic offline scorer (`--stub`, semantic overlap) so the
harness is runnable without the LLM or the real 30-CV corpus; drop `--stub` to
score through the real A4 judge on the full set.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ScoreFn = Callable[[dict[str, Any], str], float]

SPEARMAN_TARGET = 0.75
STDDEV_TARGET = 5.0

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = Path(os.environ.get("EVALS_GOLDEN") or _ROOT / "evals" / "golden" / "fixtures.json")
_REPORTS = Path(os.environ.get("EVALS_REPORTS") or _ROOT / "evals" / "reports")


def _rank(values: list[float]) -> list[float]:
    """Fractional ranks (1 = smallest), averaging ties."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n == 0 or n != len(b):
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=False))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def spearman(a: list[float], b: list[float]) -> float:
    """Spearman rank correlation = Pearson on ranks."""
    return _pearson(_rank(a), _rank(b))


def stddev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = sum(values) / n
    return math.sqrt(sum((v - m) ** 2 for v in values) / n)


def run_scoring_eval(items: list[dict[str, Any]], score_fn: ScoreFn, *, runs: int = 3) -> dict:
    """Score every golden item `runs` times; return the Spearman + stability report.

    Each item: {id, jd, cv, recruiter_score} where a higher recruiter_score is a
    better candidate.
    """
    model_means: list[float] = []
    recruiter: list[float] = []
    per_item: list[dict[str, Any]] = []
    for it in items:
        scores = [float(score_fn(it["cv"], it.get("jd", ""))) for _ in range(runs)]
        mean = sum(scores) / len(scores)
        sd = stddev(scores)
        model_means.append(mean)
        recruiter.append(float(it["recruiter_score"]))
        per_item.append({"id": it["id"], "mean": round(mean, 2), "stddev": round(sd, 3)})

    rho = spearman(model_means, recruiter)
    max_sd = max((p["stddev"] for p in per_item), default=0.0)
    passed = rho >= SPEARMAN_TARGET and max_sd < STDDEV_TARGET
    return {
        "n": len(items),
        "spearman": round(rho, 4),
        "spearman_target": SPEARMAN_TARGET,
        "max_stddev": round(max_sd, 3),
        "stddev_target": STDDEV_TARGET,
        "passed": passed,
        "per_item": per_item,
    }


def run_bias_probe(pairs: list[dict[str, Any]], score_fn: ScoreFn) -> dict:
    """Scores must be identical for identity-permuted profile pairs.

    Each pair: {id, jd, a, b} where a and b differ only in identity fields.
    """
    results = []
    ok = True
    for p in pairs:
        sa = float(score_fn(p["a"], p.get("jd", "")))
        sb = float(score_fn(p["b"], p.get("jd", "")))
        same = abs(sa - sb) < 1e-9
        ok = ok and same
        results.append({"id": p["id"], "a": sa, "b": sb, "equal": same})
    return {"passed": ok, "pairs": results}


def _load_golden() -> dict:
    if not _GOLDEN.exists():
        raise FileNotFoundError(
            f"Golden fixtures not found at {_GOLDEN}. See evals/golden/README.md."
        )
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


def _stub_score_fn() -> ScoreFn:
    """Deterministic offline scorer: semantic skills/experience overlap * 100."""
    from orchestrator.semantic import semantic_features

    def _fn(cv: dict[str, Any], jd: str) -> float:
        spec = {"must_have": cv.get("_jd_skills", []), "missions": [jd]}
        return round(semantic_features(spec, cv)["prerank_score"] * 100, 2)

    return _fn


def _judge_score_fn() -> ScoreFn:
    """Real A4 scorer through the judge (needs the LLM gateway + provider keys)."""
    from orchestrator.agents.masking import mask_cv
    from orchestrator.agents.parser import CVData
    from orchestrator.agents.scorer import score_candidate

    def _fn(cv: dict[str, Any], jd: str) -> float:
        masked = mask_cv(CVData.model_validate(cv))
        return float(score_candidate(masked, jd).overall)

    return _fn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A4 scoring + bias evaluation")
    parser.add_argument("--stub", action="store_true", help="offline deterministic scorer")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)

    golden = _load_golden()
    score_fn = _stub_score_fn() if args.stub else _judge_score_fn()

    scoring = run_scoring_eval(golden.get("items", []), score_fn, runs=args.runs)
    bias = run_bias_probe(golden.get("bias_pairs", []), score_fn)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "stub" if args.stub else "judge",
        "scoring": scoring,
        "bias": bias,
        "passed": scoring["passed"] and bias["passed"],
    }

    _REPORTS.mkdir(parents=True, exist_ok=True)
    out = _REPORTS / f"eval_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report["scoring"], indent=2))
    print(f"bias probe: {'PASS' if bias['passed'] else 'FAIL'}")
    print(f"report -> {out.relative_to(_ROOT) if out.is_relative_to(_ROOT) else out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
