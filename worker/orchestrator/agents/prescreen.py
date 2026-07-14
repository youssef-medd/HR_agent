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

from pydantic import BaseModel, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "prescreen@v1"

# Baseline questions when the application payload carries no override. Kept short
# and closed enough that a one-line WhatsApp reply answers each.
DEFAULT_QUESTIONS: list[str] = [
    "How many years of professional experience do you have relevant to this role?",
    "What is your notice period or earliest start date?",
    "What are your salary expectations for this role?",
    "Are you able to work from (or relocate to) the role's location?",
]

CONSENT_PROMPT = (
    "Hello! We'd like to ask a few quick pre-screening questions about the role "
    "you applied for. Do you consent to continue? Reply YES to proceed or NO to "
    "decline — you can stop at any time."
)


class ConsentInterpretation(BaseModel):
    consent: bool = Field(description="True only if the candidate clearly agrees to continue")


class AnswerInterpretation(BaseModel):
    answer: str = Field(default="", description="The candidate's answer, normalised to one line")
    answered: bool = Field(default=True, description="False if the reply does not answer the question")


class PrescreenError(RuntimeError):
    """Raised when a candidate reply cannot be interpreted into a schema."""


def screening_questions(app_payload: dict) -> list[str]:
    """Question list for this application — payload override, else the default set."""
    override = app_payload.get("screening_questions")
    if isinstance(override, list) and override:
        return [str(q) for q in override]
    return list(DEFAULT_QUESTIONS)


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
    "(boolean — false if the reply does not actually answer the question). "
    "Do not invent information not present in the reply. Nothing else."
)


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
