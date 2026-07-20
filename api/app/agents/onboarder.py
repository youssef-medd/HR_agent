"""A8 — smart onboarding.

Given a hired candidate and their role, generates an onboarding kit: a welcome
message, a first-day/setup checklist, a structured week-one plan, and the
documents to prepare or sign. (Handbook Q&A over a RAG index is a later slice —
this covers the deterministic plan generation.)

Like A2, A8 is a synchronous, recruiter-triggered API tool (it operates on an
already-hired application, outside the LangGraph pipeline), sharing the same
LLM gateway (`app.gateway.llm_call`, `chat` profile, deterministic).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "onboarding@v1"


class OnboardingTask(BaseModel):
    when: str = Field(default="", description="When, e.g. 'Day 1' or 'Week 1'")
    task: str = Field(default="", description="What the new hire / manager does")


class OnboardingKit(BaseModel):
    welcome_message: str = Field(default="", description="Short warm welcome note")
    checklist: list[str] = Field(
        default_factory=list, description="Pre-start / first-day setup items"
    )
    week_one_plan: list[OnboardingTask] = Field(
        default_factory=list, description="Structured first-week plan"
    )
    documents: list[str] = Field(
        default_factory=list, description="Documents to prepare or sign"
    )


class OnboardingError(RuntimeError):
    """Raised when the model output cannot be validated into an OnboardingKit."""


_SYSTEM_PROMPT = (
    "You are an HR onboarding specialist. Given a new hire's role, produce a "
    "practical onboarding kit. Rules:\n"
    "- welcome_message: a short, warm welcome (2-3 sentences) addressed to the "
    "new hire; use [first name] if no name is given.\n"
    "- checklist: 5-10 concrete pre-start / first-day setup items (accounts, "
    "hardware, access, introductions).\n"
    "- week_one_plan: 4-6 items, each with `when` ('Day 1'..'Day 5' or 'Week 1') "
    "and a specific `task` tailored to the role.\n"
    "- documents: the documents to prepare or have signed (contract, tax/ID "
    "forms, policy acknowledgements, equipment agreement).\n"
    "Keep everything role-appropriate and realistic; never invent company-"
    "specific benefits or figures.\n"
    "Respond with a single JSON object using EXACTLY these keys: welcome_message "
    "(string), checklist (array of strings), week_one_plan (array of objects with "
    "keys `when` and `task`), documents (array of strings). Nothing else."
)


def generate_onboarding_kit(
    *,
    role_title: str,
    department: str | None = None,
    candidate_name: str | None = None,
    user_id: str | None = None,
) -> OnboardingKit:
    """Generate an onboarding kit for a hired candidate via the chat gateway."""
    parts = [f"ROLE: {role_title}"]
    if department:
        parts.append(f"DEPARTMENT: {department}")
    parts.append(f"NEW HIRE NAME: {candidate_name or '(unknown — use [first name])'}")
    user_content = "\n".join(parts)

    try:
        result: OnboardingKit = llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            schema=OnboardingKit,
            user_id=user_id,
            metadata={"agent": "A8", "prompt_version": PROMPT_VERSION},
        )
    except ValidationError as exc:
        raise OnboardingError(
            f"Onboarding output did not match OnboardingKit schema: {exc}"
        ) from exc
    return result
