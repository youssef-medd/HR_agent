"""A5 — conversational pre-screening agent.

Drives the `SHORTLISTED → PRESCREENING → PRESCREENED` leg of the pipeline over
WhatsApp (the transport is stubbed in `orchestrator.side_effects` for this
slice). The conversation is a fixed screening-question set: consent is asked
first, then each question in order; `PRESCREENED` once every question is
answered. Refusal or an uninterpretable consent reply routes the application to
`NEEDS_ATTENTION` (README compliance: consent captured and timestamped before
any pre-screening).

Determinism follows the rest of the platform: the outbound message text is
templated here (not model-generated), and the LLM is used only to *interpret*
each inbound free-text reply, through the gateway's `chat` profile in JSON mode
(`temperature=0`, `seed=42`) so a persisted interpretation is reproducible from
`(model, prompt_version, seed)`.
"""

from __future__ import annotations

import json

from app.gateway import llm_call
from pydantic import BaseModel, Field, ValidationError, field_validator

PROMPT_VERSION = "prescreen@v2"
QUESTIONS_PROMPT_VERSION = "prescreen_questions@v2"
SUMMARY_PROMPT_VERSION = "prescreen_summary@v1"

# Candidate correspondence languages (spec §A5: FR/EN/AR).
_LANG_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}


def _lang_name(lang: str | None) -> str:
    return _LANG_NAMES.get((lang or "en").strip().lower()[:2], "English")

# Baseline questions when the application payload carries no override. Kept short
# and closed enough that a one-line WhatsApp reply answers each.
DEFAULT_QUESTIONS: list[str] = [
    "How many years of professional experience do you have relevant to this role?",
    "What is your notice period or earliest start date?",
    "What are your salary expectations for this role?",
    "Are you able to work from (or relocate to) the role's location?",
]

CONSENT_PROMPT = (
    "Hello! I'm an AI assistant helping with recruitment — a human recruiter makes "
    "all final decisions, and your answers are recorded for your application. We'd "
    "like to ask a few quick pre-screening questions about the role you applied "
    "for. Do you consent to continue? Reply YES to proceed or NO to decline — you "
    "can stop at any time."
)


class ConsentInterpretation(BaseModel):
    consent: bool = Field(description="True only if the candidate clearly agrees to continue")


class AnswerInterpretation(BaseModel):
    answer: str = Field(default="", description="The candidate's answer, normalised to one line")
    answered: bool = Field(default=True, description="False if the reply does not answer the question")
    sensitive: bool = Field(
        default=False,
        description="True if the reply raises a sensitive/off-script topic needing a human",
    )


class PrescreenSlots(BaseModel):
    """Structured fields extracted from the conversation, merged into the profile."""

    availability: str = Field(default="")
    notice_period: str = Field(default="")
    salary_expectation: str = Field(default="")
    mobility: str = Field(default="")


class PrescreenFlags(BaseModel):
    contradictions: list[str] = Field(default_factory=list)  # vs the CV — flagged, not judged
    red_flags: list[str] = Field(default_factory=list)
    great_signals: list[str] = Field(default_factory=list)


class PrescreenSummary(BaseModel):
    recap: str = Field(default="", description="<= 5 line recap for the recruiter")
    slots: PrescreenSlots = Field(default_factory=PrescreenSlots)
    flags: PrescreenFlags = Field(default_factory=PrescreenFlags)

    @field_validator("recap", mode="before")
    @classmethod
    def _join_recap_lines(cls, v: object) -> object:
        """Accept the recap as a list of lines.

        A "5-line recap" is naturally emitted as a JSON array; rejecting that
        threw away the whole summary — slots and flags included — because the
        caller falls back to an empty summary on any validation error.
        """
        if isinstance(v, list):
            return "\n".join(str(line).strip() for line in v if str(line).strip())
        return v


class PrescreenError(RuntimeError):
    """Raised when a candidate reply cannot be interpreted into a schema."""


def screening_questions(app_payload: dict) -> list[str]:
    """Question list for this application — payload override, else the default set."""
    override = app_payload.get("screening_questions")
    if isinstance(override, list) and override:
        return [str(q) for q in override]
    return list(DEFAULT_QUESTIONS)


class QuestionSet(BaseModel):
    questions: list[str] = Field(default_factory=list)


_QGEN_SYSTEM = (
    "You are a technical recruiter preparing a short pre-screening for a specific "
    "role. Given the job's structured spec, generate 5 to 8 concise, "
    "job-SPECIFIC screening questions a candidate can answer in one line each. "
    "Cover: 2-3 confirmations of the role's must-have skills (phrased specifically, "
    "e.g. 'Describe a RAG pipeline you built' for an AI role), plus availability / "
    "notice period, salary expectation, and mobility/location. Turn any eliminatory "
    "criteria into direct yes/no eligibility questions. Do not ask for information "
    "already obvious from a CV; ask to confirm and quantify. Respond with a single "
    'JSON object {"questions": [...]}. Nothing else.'
)


def generate_questions(
    *,
    title: str,
    job_spec: dict | None,
    lang: str | None = None,
    user_id: str | None = None,
) -> list[str]:
    """Generate job-specific screening questions from A1's JobSpec.

    Written in the candidate's language (spec §A5: FR/EN/AR). Falls back to
    `DEFAULT_QUESTIONS` when there is no structured spec or the model output
    can't be validated — pre-screening must never be blocked by the generator.
    """
    spec = (job_spec or {}).get("spec") if job_spec else None
    if not spec:
        return list(DEFAULT_QUESTIONS)

    content = (
        f"JOB TITLE: {title}\n\nJOB SPEC:\n{json.dumps(spec, ensure_ascii=False)}\n\n"
        f"Write the questions in {_lang_name(lang)}."
    )
    try:
        result: QuestionSet = llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _QGEN_SYSTEM},
                {"role": "user", "content": content},
            ],
            schema=QuestionSet,
            user_id=user_id,
            metadata={"agent": "A5", "prompt_version": QUESTIONS_PROMPT_VERSION},
        )
    except Exception:  # noqa: BLE001 — generator must never block pre-screening
        return list(DEFAULT_QUESTIONS)

    qs = [str(q).strip() for q in result.questions if str(q).strip()]
    return qs or list(DEFAULT_QUESTIONS)


_CONSENT_SYSTEM = (
    "You decide whether a job candidate consents to begin a short pre-screening "
    "conversation. You are given their raw reply. Respond with a single JSON "
    "object {\"consent\": boolean}. Set consent=true ONLY for a clear yes "
    "(e.g. 'yes', 'sure', 'ok', 'go ahead'). Anything negative, conditional, or "
    "ambiguous is false. Nothing else."
)

_ANSWER_SYSTEM = (
    "You extract a candidate's answer to a single pre-screening question from "
    "their raw reply. Respond with a single JSON object using EXACTLY these keys: "
    "answer (string — the answer normalised to one concise line), answered "
    "(boolean — false if the reply is empty, evasive, or does not actually answer "
    "the question), sensitive (boolean — true if the reply raises an off-script or "
    "sensitive topic — legal threat, health/disability, harassment, a question only "
    "a human recruiter should handle). Do not invent information not present in the "
    "reply. Nothing else."
)

_SUMMARY_SYSTEM = (
    "You summarise a completed candidate pre-screening for a recruiter. You are "
    "given the job title, the candidate's CV profile, and the question/answer "
    "pairs. Produce a single JSON object with EXACTLY these keys:\n"
    "- recap: at most 5 short lines summarising the candidate's answers.\n"
    "- slots: {availability, notice_period, salary_expectation, mobility} — the "
    "value stated by the candidate for each, or empty string if not covered.\n"
    "- flags: {contradictions, red_flags, great_signals} — arrays of short "
    "strings. contradictions = statements that conflict with the CV (state the "
    "conflict factually, do NOT judge). red_flags = concerns worth a human's "
    "attention. great_signals = notably positive signals.\n"
    "Base everything ONLY on the provided material; never invent. Write recap and "
    "flags in {lang}. Nothing else."
)


def summarize_prescreen(
    *,
    title: str,
    cv: dict,
    answers: list[dict],
    lang: str | None = None,
    user_id: str | None = None,
) -> PrescreenSummary:
    """Summarise a finished pre-screen: 5-line recap + slots + flags.

    Never blocks the pipeline — returns an empty summary on any failure.
    """
    qa = [{"q": a.get("q", ""), "a": a.get("a", "")} for a in answers]
    cv_brief = {
        "summary": cv.get("summary", ""),
        "skills": cv.get("skills", []),
        "years_experience": cv.get("years_experience"),
        "experiences": [
            {"title": e.get("title", ""), "summary": e.get("summary", "")}
            for e in cv.get("experiences", [])
        ],
    }
    content = (
        f"JOB TITLE: {title}\n\nCANDIDATE CV:\n{json.dumps(cv_brief, ensure_ascii=False)}\n\n"
        f"PRE-SCREENING Q&A:\n{json.dumps(qa, ensure_ascii=False)}"
    )
    try:
        return llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM.replace("{lang}", _lang_name(lang))},
                {"role": "user", "content": content},
            ],
            schema=PrescreenSummary,
            user_id=user_id,
            metadata={"agent": "A5", "prompt_version": SUMMARY_PROMPT_VERSION},
        )
    except Exception:  # noqa: BLE001 — summary is best-effort, never blocks
        return PrescreenSummary()


def interpret_consent(message: str, *, user_id: str | None = None) -> ConsentInterpretation:
    """Interpret a candidate's consent reply. Raises `PrescreenError` on schema drift."""
    try:
        return llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _CONSENT_SYSTEM},
                {"role": "user", "content": message},
            ],
            schema=ConsentInterpretation,
            user_id=user_id,
            metadata={"agent": "A5", "prompt_version": PROMPT_VERSION, "turn": "consent"},
        )
    except ValidationError as exc:
        raise PrescreenError(f"Consent reply did not match schema: {exc}") from exc


class SlotCoverage(BaseModel):
    """Whether an upcoming question is already answered by what was said."""

    covered: bool = Field(default=False)
    answer: str = Field(default="", description="The already-given answer, one line")


_COVERAGE_SYSTEM = (
    "You check whether a pre-screening question has ALREADY been answered by "
    "what the candidate said earlier. You get the question and the prior "
    "question/answer pairs. Respond with a single JSON object {covered, answer}. "
    "Set covered=true ONLY when an earlier reply clearly and specifically answers "
    "the new question (e.g. they already stated their notice period), and put "
    "that answer in `answer` as one concise line. If it is merely related, "
    "partial, or implied, set covered=false and answer=\"\". Never guess. "
    "Nothing else."
)


def slot_already_covered(
    question: str, prior_qa: list[dict], *, user_id: str | None = None
) -> SlotCoverage:
    """True when `question` is already answered by earlier replies (spec §A5:
    'asks only unanswered slots').

    Deterministic (temperature 0) and fail-safe: any error returns not-covered,
    so the question is asked rather than silently skipped.
    """
    if not prior_qa:
        return SlotCoverage()
    prior = json.dumps(
        [{"q": p.get("q", ""), "a": p.get("a", "")} for p in prior_qa], ensure_ascii=False
    )
    try:
        return llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _COVERAGE_SYSTEM},
                {"role": "user", "content": f"NEW QUESTION:\n{question}\n\nPRIOR Q&A:\n{prior}"},
            ],
            schema=SlotCoverage,
            user_id=user_id,
            metadata={"agent": "A5", "prompt_version": PROMPT_VERSION, "turn": "coverage"},
        )
    except Exception:  # noqa: BLE001 — never skip a slot because the check failed
        return SlotCoverage()


def interpret_answer(
    question: str, message: str, *, user_id: str | None = None
) -> AnswerInterpretation:
    """Interpret a candidate's answer to one question. Raises `PrescreenError` on schema drift."""
    try:
        return llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _ANSWER_SYSTEM},
                {"role": "user", "content": f"QUESTION:\n{question}\n\nCANDIDATE REPLY:\n{message}"},
            ],
            schema=AnswerInterpretation,
            user_id=user_id,
            metadata={"agent": "A5", "prompt_version": PROMPT_VERSION, "turn": "answer"},
        )
    except ValidationError as exc:
        raise PrescreenError(f"Answer reply did not match schema: {exc}") from exc
