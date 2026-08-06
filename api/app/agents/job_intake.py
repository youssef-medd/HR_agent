"""A1 — Job Intake & Posting.

Turns a raw job description (paste / uploaded text) into a structured JobSpec,
per-criterion scoring weights, and multichannel publication content. Runs
synchronously in the API (recruiter-triggered on a job, before any application
exists), through the shared gateway with the deterministic `judge` profile.

The JobSpec's eliminatory criteria are the hard filters A4 should enforce; the
weights are the per-criterion importance A4 scores against.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, model_validator

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
    # Sum ~100. Mirrors A4's four sub-scores (spec §A4 default 30/30/20/20) so
    # the recruiter can tune per-offer importance.
    skills: int = Field(default=30, ge=0, le=100)
    experience: int = Field(default=30, ge=0, le=100)
    education: int = Field(default=20, ge=0, le=100)
    sector: int = Field(default=20, ge=0, le=100)


class ChannelContent(BaseModel):
    linkedin_post: str = Field(default="")
    job_board_text: str = Field(default="")
    careers_page: str = Field(default="")
    whatsapp_blurb: str = Field(default="", description="≤ 2 short sentences for WhatsApp")


class JobIntake(BaseModel):
    spec: JobSpec = Field(default_factory=JobSpec)
    weights: Weights = Field(default_factory=Weights)
    channels: ChannelContent = Field(default_factory=ChannelContent)

    @model_validator(mode="before")
    @classmethod
    def _lift_flattened(cls, data: object) -> object:
        """Tolerate a flattened payload from the model.

        Models frequently emit the JobSpec fields at the top level instead of
        nested under `spec` (same for weights/channels). Without this, pydantic
        silently drops them and `spec` falls back to empty defaults.
        """
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key, model in (("spec", JobSpec), ("weights", Weights), ("channels", ChannelContent)):
            if isinstance(out.get(key), dict):
                continue
            lifted = {f: out[f] for f in model.model_fields if f in out}
            if lifted:
                out[key] = lifted
        return out
    # Careers-page tracking link (filled by the router, which knows the job id).
    tracking_link: str = Field(default="")
    # True once a recruiter has edited + saved the AI output (spec §A1 overrides).
    overridden: bool = Field(default=False)


# The six guided-intake questions (the "answer 6 questions" input mode).
GUIDED_QUESTIONS: list[dict[str, str]] = [
    {"key": "seniority", "q": "What seniority level is this role? (e.g. junior / mid / senior / lead)"},
    {"key": "mission", "q": "In one line, what will this person mainly do?"},
    {"key": "must_have", "q": "Which skills/qualifications are required? (comma-separated)"},
    {"key": "dealbreakers", "q": "Any hard dealbreakers that disqualify a candidate? (e.g. work permit, 5+ years)"},
    {"key": "location", "q": "Where is it based, and remote/hybrid/on-site?"},
    {"key": "salary", "q": "Salary range, if any? (leave blank if undisclosed)"},
]


def brief_from_answers(title: str, answers: dict[str, str]) -> str:
    """Compose a raw-JD brief from the six guided answers, for the structurer."""
    lines = [f"JOB TITLE: {title}"]
    labels = {
        "seniority": "Seniority", "mission": "Mission", "must_have": "Required",
        "dealbreakers": "Dealbreakers", "location": "Location", "salary": "Salary",
    }
    for key, label in labels.items():
        val = (answers.get(key) or "").strip()
        if val:
            lines.append(f"{label}: {val}")
    return "\n".join(lines)


class IntakeTurn(BaseModel):
    """One turn of the conversational intake: ask more, or finalize the spec."""

    done: bool = Field(default=False, description="True once enough info to finalize")
    question: str = Field(default="", description="Next clarifying question when not done")
    title: str = Field(default="", description="Proposed concise job title (when done)")
    intake: JobIntake | None = Field(default=None, description="Full spec when done")


class JobIntakeError(RuntimeError):
    """Raised when the model output cannot be validated into a JobIntake."""


_CONVERSE_SYSTEM = (
    "You are an expert recruiter helping define a job through a natural "
    "conversation. You are given an optional working title and the dialogue so "
    "far. Be warm and concise, like a helpful assistant.\n"
    "Decide: do you have enough to produce a COMPLETE JobSpec (seniority, "
    "missions, must_have, nice_to_have, languages, eliminatory_criteria), "
    "sensible scoring weights, and channel posts?\n"
    "- If NOT yet: set done=false and ask ONE short, friendly clarifying question "
    "about the single most important missing detail (question=...). intake=null.\n"
    "- If YES: set done=true, question=\"\", propose a concise `title`, and fill "
    "`intake` fully (spec + weights summing ~100 across skills/experience/"
    "education/sector + channels).\n"
    "\nHARD RULES — follow these exactly:\n"
    "1. NEVER ask a question you have already asked, even reworded. Read the "
    "conversation and check what you asked before.\n"
    "2. If the recruiter asks YOU to recommend, suggest, propose, decide, or says "
    "'you choose' / 'up to you' / 'what do you think': DO NOT ask that question "
    "again. You are the expert — infer sensible, industry-standard values yourself "
    "for that detail and move on (or finalize if nothing important is left).\n"
    "3. If an answer is vague or off-topic, do NOT re-ask. Infer a reasonable "
    "professional default and continue.\n"
    "4. Ask AT MOST 3 questions in the whole conversation. After that you must "
    "set done=true and fill in anything still missing with sensible defaults for "
    "the role and seniority.\n"
    "5. If the recruiter says finalize / proceed / save / go ahead, immediately "
    "set done=true.\n"
    "\nYou may infer standard responsibilities, nice-to-haves and eliminatory "
    "criteria for the role — that is expected expertise, not invention. Only "
    "salary and company-specific facts must never be invented (leave empty).\n"
    "\nWhen done=true, `intake` MUST use this exact nested shape (do NOT flatten "
    "the spec fields to the top level of intake):\n"
    '{"done": true, "question": "", "title": "...", "intake": {'
    '"spec": {"seniority": "...", "location": "...", "salary_range": "", '
    '"missions": [...], "must_have": [...], "nice_to_have": [...], '
    '"languages": [...], "eliminatory_criteria": [...]}, '
    '"weights": {"skills": 30, "experience": 30, "education": 20, "sector": 20}, '
    '"channels": {"linkedin_post": "...", "job_board_text": "...", '
    '"careers_page": "...", "whatsapp_blurb": "..."}}}\n'
    "Never leave missions or must_have empty when done=true. Respond with a "
    "single JSON object. Nothing else."
)


MAX_INTAKE_QUESTIONS = 3

# Recruiter phrases that mean "stop asking, you decide".
_DEFER_PHRASES = (
    "recommend", "suggest", "you choose", "up to you", "your call", "you decide",
    "what do you think", "propose", "whatever you", "you pick", "surprise me",
)


def converse_intake(
    title: str, transcript: list[dict[str, str]], *, user_id: str | None = None
) -> IntakeTurn:
    """One conversational-intake step: ask the next question, or finalize the spec.

    `transcript` is the dialogue so far as [{role: 'assistant'|'user', text}].
    `title` may be empty (from-scratch AI creation) — the AI proposes one.

    Guards against the model looping: once it has asked `MAX_INTAKE_QUESTIONS`,
    or the recruiter defers the decision back to it, finalization is forced.
    """
    convo = "\n".join(f"{m.get('role', 'user')}: {m.get('text', '')}" for m in transcript)

    asked = sum(1 for m in transcript if m.get("role") == "assistant")
    last_user = next(
        (m.get("text", "") for m in reversed(transcript) if m.get("role") == "user"), ""
    ).lower()
    defers = any(p in last_user for p in _DEFER_PHRASES)

    directive = ""
    if asked >= MAX_INTAKE_QUESTIONS or defers:
        directive = (
            "\n\nIMPORTANT: You must NOT ask another question now. Set done=true and "
            "produce the complete draft, filling anything still unknown with sensible "
            "professional defaults for this role and seniority."
        )

    content = (
        f"WORKING TITLE: {title or '(none — propose one)'}\n\n"
        f"CONVERSATION SO FAR:\n{convo or '(none yet)'}"
        f"\n\nQuestions you have already asked: {asked} (limit {MAX_INTAKE_QUESTIONS})."
        f"{directive}"
    )
    try:
        return llm_call(
            profile="judge",
            messages=[
                {"role": "system", "content": _CONVERSE_SYSTEM},
                {"role": "user", "content": content},
            ],
            schema=IntakeTurn,
            user_id=user_id,
            metadata={"agent": "A1", "prompt_version": PROMPT_VERSION, "stage": "converse"},
        )
    except ValidationError as exc:
        raise JobIntakeError(f"Intake-turn output did not match schema: {exc}") from exc


_SYSTEM_PROMPT = (
    "You are an expert technical recruiter. Given a job title and a raw job "
    "description, produce a single JSON object with three parts:\n"
    "1) spec: seniority, location, salary_range (empty if unknown), missions, "
    "must_have, nice_to_have, languages, eliminatory_criteria (hard requirements "
    "that disqualify a candidate if unmet — keep this list tight and only truly "
    "disqualifying items). Phrase every eliminatory criterion POSITIVELY, as a "
    "requirement the candidate must MEET ('Basic programming experience', "
    "'Fluent English'), never as a negative problem ('No programming experience', "
    "'Lack of English') — the scorer reads them as requirements.\n"
    "2) weights: integer importance for skills, experience, education, sector "
    "(sector = domain/industry-context fit) that sum to about 100, reflecting "
    "THIS role.\n"
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
