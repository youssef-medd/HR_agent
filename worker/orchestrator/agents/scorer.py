"""A4 — scoring judge.

Scores one masked candidate against a job description and returns a structured
fit assessment. Uses the `judge` profile (MODEL_JUDGE) through the gateway in
JSON mode, deterministic (`temperature=0`, `seed=42`) so a persisted score is
reproducible from `(model, prompt_version, seed)`.

Constraints from the spec:
- The input is already identity-masked (`agents.masking.mask_cv`); this module
  never receives a name, contact detail, or institution proper name.
- One candidate per prompt (ADR-005) — no pairwise comparison.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "cv_score@v2"

Recommendation = Literal["shortlist", "pool", "decline"]


class ScoreResult(BaseModel):
    # populate_by_name + alias choices tolerate the judge naming a field
    # `overall_score`/`summary` instead of `overall`/`rationale`.
    model_config = ConfigDict(populate_by_name=True)

    overall: int = Field(
        ge=0, le=100, description="Overall fit score 0-100",
        validation_alias=AliasChoices("overall", "overall_score", "score"),
    )
    skills_match: int = Field(default=0, ge=0, le=100)
    experience_match: int = Field(default=0, ge=0, le=100)
    education_match: int = Field(default=0, ge=0, le=100)
    rationale: str = Field(
        default="", description="Short justification, identity-blind",
        validation_alias=AliasChoices("rationale", "summary", "justification"),
    )
    recommendation: Recommendation = Field(default="pool")


class ScoreError(RuntimeError):
    """Raised when the judge output cannot be validated into a ScoreResult."""


_SYSTEM_PROMPT = (
    "You are a fair, identity-blind hiring judge. You receive a candidate's "
    "job-relevant profile (skills, experience, education — no name, contact, or "
    "institution) and a job description. Score each dimension against THIS job "
    "using the anchored rubric below. Base scores only on evidence in the "
    "profile; do not speculate about protected attributes.\n"
    "Rubric per dimension (skills_match, experience_match, education_match):\n"
    "- 85-100: meets every stated requirement in this dimension, with depth\n"
    "- 70-84: meets most requirements; gaps are minor or trainable\n"
    "- 50-69: partial overlap; several requirements unmet\n"
    "- 25-49: weak overlap; only tangential evidence\n"
    "- 0-24: no relevant evidence\n"
    "In the rationale, name the specific requirements that are met and missing.\n"
    "Respond with a single JSON object using EXACTLY these keys: "
    "overall (int 0-100), skills_match (int 0-100), experience_match (int 0-100), "
    "education_match (int 0-100), rationale (string), recommendation "
    "('shortlist'|'pool'|'decline'). Nothing else."
)

# Deterministic weighting — the persisted `overall` and `recommendation` are
# computed here, not taken from the model. Skills dominate; education matters
# least (spec: projects and shipped work over pedigree).
_WEIGHTS = {"skills_match": 0.50, "experience_match": 0.35, "education_match": 0.15}
_SHORTLIST_AT = 70
_POOL_AT = 45


def _finalize(raw: ScoreResult) -> ScoreResult:
    """Recompute overall + recommendation from sub-scores with fixed weights."""
    overall = round(
        raw.skills_match * _WEIGHTS["skills_match"]
        + raw.experience_match * _WEIGHTS["experience_match"]
        + raw.education_match * _WEIGHTS["education_match"]
    )
    recommendation: Recommendation = (
        "shortlist" if overall >= _SHORTLIST_AT else "pool" if overall >= _POOL_AT else "decline"
    )
    return raw.model_copy(update={"overall": overall, "recommendation": recommendation})


def score_candidate(
    masked_cv: dict[str, Any],
    jd_text: str | None,
    *,
    user_id: str | None = None,
) -> ScoreResult:
    """Score a masked candidate against a job description via the judge model."""
    jd = (jd_text or "").strip()
    jd_block = jd if jd else "(No job description provided — score general seniority and strength.)"

    user_content = (
        f"JOB DESCRIPTION:\n{jd_block}\n\n"
        f"CANDIDATE PROFILE (identity-masked):\n{json.dumps(masked_cv, ensure_ascii=False)}"
    )

    try:
        result: ScoreResult = llm_call(
            profile="judge",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            schema=ScoreResult,
            user_id=user_id,
            metadata={"agent": "A4", "prompt_version": PROMPT_VERSION, "has_jd": bool(jd)},
        )
    except ValidationError as exc:
        raise ScoreError(f"Judge output did not match ScoreResult schema: {exc}") from exc
    return _finalize(result)
