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
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ScoreFn = Callable[[dict[str, Any], str], float]

SPEARMAN_TARGET = 0.75
STDDEV_TARGET = 5.0
# Spec §A3 ACs: >=95% of files parse without a blocking error, and field
# accuracy >=90% on the reference corpus.
PARSE_SUCCESS_TARGET = 0.95
FIELD_ACCURACY_TARGET = 0.90
# Spec §A5 AC: 80% of the scripted dialogues complete without human help.
DIALOGUE_COMPLETION_TARGET = 0.80

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = Path(os.environ.get("EVALS_GOLDEN") or _ROOT / "evals" / "golden" / "fixtures.json")
_DIALOGUES = Path(
    os.environ.get("EVALS_DIALOGUES") or _ROOT / "evals" / "golden" / "dialogues.json"
)
_REPORTS = Path(os.environ.get("EVALS_REPORTS") or _ROOT / "evals" / "reports")
_CVS = Path(os.environ.get("EVALS_CVS") or _ROOT / "evals" / "golden" / "cvs")


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


# --- A3 parser eval (§5.4 "évals parseur") ----------------------------------


def _norm_field(value: Any) -> Any:
    """Compare contact fields on substance, not punctuation.

    Phone numbers are written every possible way — `+216 24 118 903`,
    `00216 55 302 887`, `21 6 - 92 - 664 - 105` — so digits are compared, with
    an international prefix normalised away. Emails compare case-insensitively.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [_norm_field(v) for v in value]
    text = str(value).strip()
    if not text:
        return None
    if "@" in text:
        return text.lower()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        # 00216… and +216… are the same number; keep the last 8 significant digits.
        return digits[-8:]
    return text.lower()


def _field_matches(expected: Any, actual: Any) -> bool:
    """True when the parsed value carries the expected content."""
    exp, act = _norm_field(expected), _norm_field(actual)
    if exp is None:
        # `09_missing_email` asserts the parser returns nothing rather than
        # inventing an address from a URL.
        return act is None
    if isinstance(exp, list):
        return any(e == act for e in exp)
    if isinstance(act, list):
        return exp in act
    if exp == act:
        return True
    # Names: accept case/accent-insensitive equality on the collapsed form, so
    # "Omar Ben Salah" still matches "OMAR BEN SALAH".
    return str(exp).replace(" ", "") == str(act).replace(" ", "")


# --- field extraction & comparison ------------------------------------------
#
# The spec (§5.4) wants field accuracy on names, **dates, job titles and
# skills** — not just contact details. The manifest states ground truth the way
# a recruiter reads a CV (`employers`, `education`, `title`), while the parser
# emits nested records (`experiences[].company`, `education[].institution`), so
# each checked field pairs an extractor with a comparator.

# A list field counts as a hit when the parser recovered this share of the
# expected entries. Recall, not precision: a CV legitimately lists more skills
# than the manifest bothers to enumerate.
LIST_RECALL_TARGET = 0.7
# Tolerance on total years of experience — CVs rarely state it, it is inferred
# from date ranges, and a half-year of rounding is not an error.
YEARS_TOLERANCE = 1.5


def _fold(text: Any) -> str:
    """Accent/case/punctuation-insensitive comparison form."""
    raw = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in raw if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _text_hit(expected: Any, actual: Any) -> bool:
    """Containment either way on the folded form.

    "Senior Backend Engineer" matches "Senior Backend Engineer (Payments)", and
    "ENSI" matches "ENSI Manouba" — a parser that keeps more of the source line
    than the manifest records has not made a mistake.
    """
    exp, act = _fold(expected), _fold(actual)
    if not exp or not act:
        return False
    return exp in act or act in exp


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _experiences(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in _as_list(profile.get("experiences")) if isinstance(e, dict)]


def _employers(profile: dict[str, Any]) -> list[str]:
    return [str(e.get("company") or "") for e in _experiences(profile)]


def _institutions(profile: dict[str, Any]) -> list[str]:
    return [
        str(e.get("institution") or "")
        for e in _as_list(profile.get("education"))
        if isinstance(e, dict)
    ]


# Folded ASCII markers of an ongoing role, plus the non-latin ones matched on
# the raw text (folding strips non-latin scripts to nothing, and an empty
# needle would match every value).
_PRESENT = ("present", "actuel", "current", "now", "aujourd", "ongoing", "en cours")
_PRESENT_RAW = ("حالي", "الآن")


def _is_present(end: Any) -> bool:
    text = str(end or "")
    folded = _fold(text)
    if not folded and not text.strip():
        return True  # an empty end date means the role is ongoing
    return any(p in folded for p in _PRESENT) or any(p in text for p in _PRESENT_RAW)


def _current_employer(profile: dict[str, Any]) -> str:
    """The employer of the ongoing role, else the first listed (CVs run newest-first)."""
    experiences = _experiences(profile)
    for exp in experiences:
        if _is_present(exp.get("end")):
            return str(exp.get("company") or "")
    return str(experiences[0].get("company") or "") if experiences else ""


def _titles(profile: dict[str, Any]) -> list[str]:
    return [str(e.get("title") or "") for e in _experiences(profile)]


_YEAR = re.compile(r"(19|20)\d{2}")


def _dates_ok(profile: dict[str, Any]) -> bool:
    """Structural date check on the extracted experience timeline.

    There is no per-experience date ground truth in the manifest, so this
    asserts what a correct extraction must satisfy regardless of the CV: every
    experience carries a start date containing a year, and its end is either
    ongoing or a year not earlier than the start.
    """
    experiences = _experiences(profile)
    if not experiences:
        return False
    for exp in experiences:
        start = _YEAR.search(str(exp.get("start") or ""))
        if start is None:
            return False
        if _is_present(exp.get("end")):
            continue
        end = _YEAR.search(str(exp.get("end") or ""))
        if end is None or int(end.group()) < int(start.group()):
            return False
    return True


def list_recall(expected: Any, actual: Any) -> float:
    """Share of the expected entries the parser recovered (0.0–1.0)."""
    wanted = [e for e in _as_list(expected) if _fold(e)]
    if not wanted:
        return 1.0
    got = _as_list(actual)
    return sum(any(_text_hit(w, g) for g in got) for w in wanted) / len(wanted)


def _years_hit(expected: Any, actual: Any) -> bool:
    try:
        return abs(float(expected) - float(actual)) <= YEARS_TOLERANCE
    except (TypeError, ValueError):
        return False


# field -> (manifest key or None for a structural check, extractor, comparator)
_CHECKS: dict[str, tuple[str | None, Callable[[dict], Any], Callable[[Any, Any], bool]]] = {
    "full_name": ("full_name", lambda p: p.get("full_name"), _field_matches),
    "email": ("email", lambda p: p.get("email"), _field_matches),
    "phone": ("phone", lambda p: p.get("phone"), _field_matches),
    "location": ("location", lambda p: p.get("location"), _text_hit),
    "title": ("title", _titles, lambda exp, act: any(_text_hit(exp, t) for t in act)),
    "current_employer": ("current_employer", _current_employer, _text_hit),
    "employers": (
        "employers", _employers, lambda e, a: list_recall(e, a) >= LIST_RECALL_TARGET
    ),
    "education": (
        "education", _institutions, lambda e, a: list_recall(e, a) >= LIST_RECALL_TARGET
    ),
    "skills": (
        "skills", lambda p: p.get("skills"),
        lambda e, a: list_recall(e, a) >= LIST_RECALL_TARGET,
    ),
    "languages": (
        "languages", lambda p: p.get("languages"),
        lambda e, a: list_recall(e, a) >= LIST_RECALL_TARGET,
    ),
    "certifications": (
        "certifications", lambda p: p.get("certifications"),
        lambda e, a: list_recall(e, a) >= LIST_RECALL_TARGET,
    ),
    "years_experience": ("years_experience", lambda p: p.get("years_experience"), _years_hit),
    # No manifest key: a structural assertion on the extracted timeline.
    "dates": (None, _dates_ok, lambda _exp, act: bool(act)),
}

DEFAULT_PARSER_FIELDS: tuple[str, ...] = (
    "full_name",
    "email",
    "phone",
    "location",
    "title",
    "current_employer",
    "employers",
    "education",
    "skills",
    "languages",
    "certifications",
    "years_experience",
    "dates",
)


def run_parser_eval(
    parse_fn: Callable[[str, bytes], dict[str, Any]],
    *,
    cv_dir: Path | None = None,
    fields: tuple[str, ...] = DEFAULT_PARSER_FIELDS,
) -> dict:
    """Parse every CV in the reference corpus and score it against the manifest.

    `manifest.json` carries the ground truth per file. Files marked as an exact
    duplicate are skipped: they are a file-hash concern before parsing, not a
    parser-accuracy one.

    Accuracy is the share of checked (file, field) pairs the parser got right,
    across contact fields, job titles, employers, education, skills, languages
    and the experience timeline (§5.4).
    """
    base = cv_dir or _CVS
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))

    per_file: list[dict[str, Any]] = []
    parsed_ok = 0
    considered = 0
    field_hits = 0
    field_total = 0
    by_field: dict[str, dict[str, int]] = {}

    for entry in manifest["files"]:
        name = entry["file"]
        if entry.get("duplicate_type") == "exact":
            continue
        considered += 1
        expected = entry.get("expected")
        if not isinstance(expected, dict):
            continue

        row: dict[str, Any] = {"file": name}
        try:
            profile = parse_fn(name, (base / name).read_bytes())
            parsed_ok += 1
        except Exception as exc:  # noqa: BLE001 — a parse failure is a result
            row["error"] = f"{type(exc).__name__}: {exc}"[:160]
            per_file.append(row)
            continue

        checks: dict[str, bool] = {}
        for field in fields:
            spec = _CHECKS.get(field)
            if spec is None:
                continue
            key, extract, compare = spec
            if key is not None and key not in expected:
                continue
            want = expected.get(key) if key is not None else None
            got = extract(profile)
            ok = bool(compare(want, got))
            checks[field] = ok
            field_hits += int(ok)
            field_total += 1
            tally = by_field.setdefault(field, {"checked": 0, "hits": 0})
            tally["checked"] += 1
            tally["hits"] += int(ok)
            if not ok:
                row[f"{field}_got"] = got
                row[f"{field}_want"] = want
        row["checks"] = checks
        per_file.append(row)

    parse_rate = parsed_ok / considered if considered else 0.0
    accuracy = field_hits / field_total if field_total else 0.0
    return {
        "n": considered,
        "parsed": parsed_ok,
        "parse_success": round(parse_rate, 4),
        "parse_success_target": PARSE_SUCCESS_TARGET,
        "field_accuracy": round(accuracy, 4),
        "field_accuracy_target": FIELD_ACCURACY_TARGET,
        "fields_checked": field_total,
        "fields": sorted(by_field),
        "by_field": {
            f: {
                **t,
                "accuracy": round(t["hits"] / t["checked"], 4) if t["checked"] else 0.0,
            }
            for f, t in sorted(by_field.items())
        },
        "passed": parse_rate >= PARSE_SUCCESS_TARGET and accuracy >= FIELD_ACCURACY_TARGET,
        "per_file": per_file,
    }


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


def _live_parse_fn():
    """Real A3 path: extract text, then parse through the LLM gateway."""
    from orchestrator.agents.parser import extract_text, parse_cv

    def _parse(filename: str, data: bytes) -> dict[str, Any]:
        return parse_cv(extract_text(filename, data)).model_dump()

    return _parse


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
    parser.add_argument(
        "--parser", action="store_true", help="run the A3 parser eval on the CV corpus instead"
    )
    parser.add_argument(
        "--fields",
        default="",
        help="comma-separated subset of parser fields to check "
        f"(default: {','.join(DEFAULT_PARSER_FIELDS)})",
    )
    args = parser.parse_args(argv)

    if args.parser:
        fields = (
            tuple(f.strip() for f in args.fields.split(",") if f.strip())
            or DEFAULT_PARSER_FIELDS
        )
        unknown = [f for f in fields if f not in _CHECKS]
        if unknown:
            parser.error(f"unknown field(s): {', '.join(unknown)}")
        result = run_parser_eval(_live_parse_fn(), fields=fields)
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "live",
            "parser": result,
            "passed": result["passed"],
        }
        out = _write_report(report, "parser")
        print(
            json.dumps(
                {k: result[k] for k in (
                    "n", "parsed", "parse_success", "parse_success_target",
                    "field_accuracy", "field_accuracy_target", "fields_checked",
                    "by_field", "passed",
                )},
                indent=2,
            )
        )
        misses = [
            f for f in result["per_file"]
            if f.get("error") or not all(f.get("checks", {}).values())
        ]
        if misses:
            print("\nfiles with a miss:")
            for f in misses:
                if f.get("error"):
                    print(f"  {f['file']}: {f['error']}")
                    continue
                bad = [k for k, ok in f["checks"].items() if not ok]
                for field in bad:
                    print(
                        f"  {f['file']}: {field} -> got {f.get(field + '_got')!r}, "
                        f"want {f.get(field + '_want')!r}"
                    )
        print(f"report -> {_rel(out)}")
        return 0 if result["passed"] else 1

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
