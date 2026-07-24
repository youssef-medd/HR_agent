"""A1 — Job Intake & Posting.

Turns a raw job description (paste / uploaded text) into a structured JobSpec,
per-criterion scoring weights, and multichannel publication content. Runs
synchronously in the API (recruiter-triggered on a job, before any application
exists), through the shared gateway with the deterministic `judge` profile.

The JobSpec's eliminatory criteria are the hard filters A4 should enforce; the
weights are the per-criterion importance A4 scores against.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "job_intake@v1"


class JobSpec(BaseModel):
    seniority: str = Field(default="", description="e.g. junior / mid / senior / lead")
    location: str = Field(default="")
    salary_range: str = Field(default="", description="As stated or a reasonable estimate, else empty")
    missions: list[str] = Field(default_factory=list, description="Core responsibilities")
    must_have: list[str] = Field(default_factory=list, description="Required skills/qualifications")
    nice_to_have: list[str] = Field(default_factory=list, description="Bonus skills")
    languages: list[str] = Field(default_factory=list)
    eliminatory_criteria: list[str] = Field(
        default_factory=list,
        description="Hard requirements that disqualify if unmet (e.g. work permit, required language)",
    )


class Weights(BaseModel):
    # Sum ~100. Mirrors A4's sub-scores so the recruiter can tune importance.
    skills: int = Field(default=50, ge=0, le=100)
    experience: int = Field(default=35, ge=0, le=100)
    education: int = Field(default=15, ge=0, le=100)


class ChannelContent(BaseModel):
    linkedin_post: str = Field(default="")
    job_board_text: str = Field(default="")
    careers_page: str = Field(default="")
    whatsapp_blurb: str = Field(default="", description="≤ 2 short sentences for WhatsApp")


class JobIntake(BaseModel):
    spec: JobSpec = Field(default_factory=JobSpec)
    weights: Weights = Field(default_factory=Weights)
    channels: ChannelContent = Field(default_factory=ChannelContent)


class JobIntakeError(RuntimeError):
    """Raised when the model output cannot be validated into a JobIntake."""


_SYSTEM_PROMPT = (
    "You are an expert technical recruiter. Given a job title and a raw job "
    "description, produce a single JSON object with three parts:\n"
    "1) spec: seniority, location, salary_range (empty if unknown), missions, "
    "must_have, nice_to_have, languages, eliminatory_criteria (hard requirements "
    "that disqualify a candidate if unmet — keep this list tight and only truly "
    "disqualifying items).\n"
    "2) weights: integer importance for skills, experience, education that sum to "
    "about 100, reflecting THIS role.\n"
    "3) channels: ready-to-post content — linkedin_post (engaging, with hashtags), "
    "job_board_text (neutral, structured), careers_page (warm, on-brand), "
    "whatsapp_blurb (max 2 short sentences).\n"
    "Base everything only on the provided description; never invent salary or "
    "requirements that are not implied. Respond with JSON only, matching the "
    "requested schema. Nothing else."
)


def structure_job(*, title: str, raw_jd: str, user_id: str | None = None) -> JobIntake:
    """Structure a raw JD into a JobIntake (spec + weights + channels)."""
    content = f"JOB TITLE: {title}\n\nRAW JOB DESCRIPTION:\n{raw_jd or '(none provided)'}"
    try:
        result: JobIntake = llm_call(
            profile="judge",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            schema=JobIntake,
            user_id=user_id,
            metadata={"agent": "A1", "prompt_version": PROMPT_VERSION},
        )
    except ValidationError as exc:
        raise JobIntakeError(f"Job-intake output did not match JobIntake schema: {exc}") from exc
    return result
