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
# Spec §A5 AC: 80% of the scripted dialogues complete without human help.
DIALOGUE_COMPLETION_TARGET = 0.80

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = Path(os.environ.get("EVALS_GOLDEN") or _ROOT / "evals" / "golden" / "fixtures.json")
_DIALOGUES = Path(
    os.environ.get("EVALS_DIALOGUES") or _ROOT / "evals" / "golden" / "dialogues.json"
)
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


# --- A5 scripted dialogue eval ----------------------------------------------


def run_dialogue(
    dialogue: dict[str, Any], *, consent_fn, answer_fn, coverage_fn
) -> dict[str, Any]:
    """Replay one scripted dialogue through the A5 rules.

    Mirrors `nodes.prescreen_node`: consent first, skip already-covered slots,
    one clarification re-ask, sensitive reply -> handover. Returns the outcome
    (`complete` | `no_consent` | `handoff` | `unclear` | `ran_out`) plus the
    slots that were filled.
    """
    questions: list[str] = list(dialogue.get("questions") or [])
    replies: list[str] = list(dialogue.get("replies") or [])

    if not consent_fn(dialogue.get("consent_reply", "")).consent:
        return {"id": dialogue.get("id"), "outcome": "no_consent", "answers": [], "asked": 0}

    answers: list[dict[str, Any]] = []
    # Raw replies verbatim — the coverage check needs what was actually said,
    # not the answer normalised to a single question (mirrors prescreen_node).
    raw_qa: list[dict[str, Any]] = []
    asked = 0
    ri = 0
    for question in questions:
        # Slot-filling: skip what an earlier reply already answered.
        if raw_qa:
            cov = coverage_fn(question, raw_qa)
            if cov.covered and cov.answer:
                answers.append({"q": question, "a": cov.answer, "auto": True})
                continue

        if ri >= len(replies):
            return {
                "id": dialogue.get("id"), "outcome": "ran_out",
                "answers": answers, "asked": asked,
            }
        raw_qa.append({"q": question, "a": replies[ri]})
        interp = answer_fn(question, replies[ri])
        ri += 1
        asked += 1

        if interp.sensitive:
            return {
                "id": dialogue.get("id"), "outcome": "handoff",
                "answers": answers, "asked": asked,
            }

        # One clarification re-ask, exactly as the node does.
        if not interp.answered:
            if ri >= len(replies):
                return {
                    "id": dialogue.get("id"), "outcome": "unclear",
                    "answers": answers, "asked": asked,
                }
            raw_qa.append({"q": question, "a": replies[ri]})
            interp = answer_fn(question, replies[ri])
            ri += 1
            asked += 1
            if interp.sensitive:
                return {
                    "id": dialogue.get("id"), "outcome": "handoff",
                    "answers": answers, "asked": asked,
                }
            if not interp.answered:
                return {
                    "id": dialogue.get("id"), "outcome": "unclear",
                    "answers": answers, "asked": asked,
                }

        answers.append({"q": question, "a": interp.answer})

    return {"id": dialogue.get("id"), "outcome": "complete", "answers": answers, "asked": asked}


def run_dialogue_eval(
    dialogues: list[dict[str, Any]], *, consent_fn, answer_fn, coverage_fn
) -> dict[str, Any]:
    """Run every scripted dialogue and score against the §A5 acceptance criteria.

    Measures the completion rate over the dialogues expected to complete, and
    checks that a completed dialogue stored every slot.
    """
    results: list[dict[str, Any]] = []
    for d in dialogues:
        got = run_dialogue(d, consent_fn=consent_fn, answer_fn=answer_fn, coverage_fn=coverage_fn)
        expected = d.get("expect", "complete")
        n_q = len(d.get("questions") or [])
        slots_ok = len(got["answers"]) == n_q if got["outcome"] == "complete" else True
        results.append({
            **got,
            "lang": d.get("lang", ""),
            "expected": expected,
            "matched": got["outcome"] == expected,
            "slots_stored": f"{len(got['answers'])}/{n_q}",
            "slots_ok": slots_ok,
        })

    expect_complete = [r for r in results if r["expected"] == "complete"]
    completed = [r for r in expect_complete if r["outcome"] == "complete"]
    rate = len(completed) / len(expect_complete) if expect_complete else 0.0
    controls = [r for r in results if r["expected"] != "complete"]

    all_slots_ok = all(r["slots_ok"] for r in results)
    controls_ok = all(r["matched"] for r in controls)
    passed = rate >= DIALOGUE_COMPLETION_TARGET and all_slots_ok and controls_ok

    by_lang: dict[str, dict[str, int]] = {}
    for r in expect_complete:
        b = by_lang.setdefault(r["lang"] or "??", {"total": 0, "complete": 0})
        b["total"] += 1
        if r["outcome"] == "complete":
            b["complete"] += 1

    return {
        "n": len(expect_complete),
        "completed": len(completed),
        "completion_rate": round(rate, 4),
        "completion_target": DIALOGUE_COMPLETION_TARGET,
        "all_slots_stored": all_slots_ok,
        "controls_ok": controls_ok,
        "by_language": by_lang,
        "passed": passed,
        "per_dialogue": [
            {k: r[k] for k in ("id", "lang", "expected", "outcome", "matched", "slots_stored")}
            for r in results
        ],
    }


def _load_dialogues() -> list[dict[str, Any]]:
    if not _DIALOGUES.exists():
        raise FileNotFoundError(f"Scripted dialogues not found at {_DIALOGUES}.")
    return json.loads(_DIALOGUES.read_text(encoding="utf-8")).get("dialogues", [])


def _stub_dialogue_fns():
    """Deterministic offline interpreters so the harness runs without the LLM."""
    from orchestrator.agents.prescreen import (
        AnswerInterpretation,
        ConsentInterpretation,
        SlotCoverage,
    )

    yes = ("yes", "yeah", "ok", "sure", "oui", "daccord", "d'accord", "نعم", "go ahead", "confirme")
    vague = ("hmm", "euh", "dunno", "sais pas", "not sure", "???")
    sensitive = ("lawyer", "avocat", "discrimination", "harassment")

    def consent_fn(text: str) -> ConsentInterpretation:
        low = (text or "").lower()
        agreed = any(w in low for w in yes) and not low.strip().startswith("no")
        return ConsentInterpretation(consent=agreed)

    def answer_fn(question: str, reply: str) -> AnswerInterpretation:
        low = (reply or "").lower()
        if any(w in low for w in sensitive):
            return AnswerInterpretation(answer=reply, answered=True, sensitive=True)
        if not reply.strip() or any(low.strip().startswith(v) for v in vague):
            return AnswerInterpretation(answer="", answered=False)
        return AnswerInterpretation(answer=reply.strip(), answered=True)

    def coverage_fn(question: str, prior: list[dict]) -> SlotCoverage:
        # Offline heuristic: a prior reply mentioning a duration covers a
        # notice/availability question.
        joined = " ".join(str(p.get("a", "")) for p in prior).lower()
        wants_notice = any(
            w in question.lower() for w in ("notice", "préavis", "preavis", "إشعار", "start")
        )
        mentions = any(
            w in joined
            for w in ("month", "mois", "week", "semaine", "شهر", "start in", "disponible")
        )
        if wants_notice and mentions:
            return SlotCoverage(covered=True, answer="(from earlier reply)")
        return SlotCoverage()

    return consent_fn, answer_fn, coverage_fn


def _live_dialogue_fns():
    """The real A5 interpreters (LLM gateway)."""
    from orchestrator.agents.prescreen import (
        interpret_answer,
        interpret_consent,
        slot_already_covered,
    )

    return (
        lambda t: interpret_consent(t),
        lambda q, r: interpret_answer(q, r),
        lambda q, prior: slot_already_covered(q, prior),
    )


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


def _write_report(report: dict[str, Any], prefix: str) -> Path:
    _REPORTS.mkdir(parents=True, exist_ok=True)
    out = _REPORTS / f"{prefix}_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _rel(path: Path) -> str:
    return str(path.relative_to(_ROOT) if path.is_relative_to(_ROOT) else path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A4 scoring/bias + A5 dialogue evaluation")
    parser.add_argument("--stub", action="store_true", help="offline deterministic interpreters")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--dialogues", action="store_true", help="run the A5 scripted-dialogue eval instead"
    )
    args = parser.parse_args(argv)

    if args.dialogues:
        consent_fn, answer_fn, coverage_fn = (
            _stub_dialogue_fns() if args.stub else _live_dialogue_fns()
        )
        result = run_dialogue_eval(
            _load_dialogues(),
            consent_fn=consent_fn,
            answer_fn=answer_fn,
            coverage_fn=coverage_fn,
        )
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "stub" if args.stub else "live",
            "dialogues": result,
            "passed": result["passed"],
        }
        out = _write_report(report, "dialogues")
        print(
            json.dumps(
                {k: result[k] for k in (
                    "n", "completed", "completion_rate", "completion_target",
                    "all_slots_stored", "controls_ok", "by_language", "passed",
                )},
                indent=2,
            )
        )
        failures = [d for d in result["per_dialogue"] if not d["matched"]]
        if failures:
            print("\nnot matching expectation:")
            for f in failures:
                print(f"  {f['id']} ({f['lang']}): expected {f['expected']}, got {f['outcome']}")
        print(f"report -> {_rel(out)}")
        return 0 if result["passed"] else 1

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
    out = _write_report(report, "eval")

    print(json.dumps(report["scoring"], indent=2))
    print(f"bias probe: {'PASS' if bias['passed'] else 'FAIL'}")
    print(f"report -> {_rel(out)}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
