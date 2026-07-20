"""A2 — sourcing assistant.

Given a job posting, produces a recruiter sourcing kit: a boolean search string
(for LinkedIn Recruiter / Google X-ray), the core keywords, suggested platforms,
and a short outreach draft the recruiter personalises and sends manually
(LinkedIn-assist — no automated outreach).

Unlike the pipeline agents (A1/A4/A5/A6), A2 does not run inside the LangGraph
worker: it operates on a *job* before any application exists and is triggered
synchronously from the API, so it lives in the API package. It shares the same
LLM gateway (`app.gateway.llm_call`, `chat` profile, deterministic).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.gateway import llm_call

PROMPT_VERSION = "sourcing@v1"


class SourcingKit(BaseModel):
    boolean_search: str = Field(
        default="", description="Ready-to-paste boolean query for LinkedIn/Google X-ray"
    )
    keywords: list[str] = Field(
        default_factory=list, description="Core skills/titles to search on"
    )
    platforms: list[str] = Field(
        default_factory=list, description="Suggested sourcing platforms"
    )
    outreach_subject: str = Field(default="", description="Short outreach subject line")
    outreach_message: str = Field(
        default="", description="Personalisable outreach draft (with [placeholders])"
    )


class SourcingError(RuntimeError):
    """Raised when the model output cannot be validated into a SourcingKit."""


_SYSTEM_PROMPT = (
    "You are an expert technical sourcer. Given a job posting, produce a practical "
    "sourcing kit a recruiter can act on immediately. Rules:\n"
    "- boolean_search: ONE ready-to-paste boolean string usable in LinkedIn "
    "Recruiter or a Google X-ray (e.g. site:linkedin.com/in). Combine role titles "
    "and must-have skills with AND/OR and parentheses.\n"
    "- keywords: the 6-12 most discriminating skills/titles for this role.\n"
    "- platforms: where these candidates are found (e.g. LinkedIn, GitHub, "
    "Stack Overflow, Kaggle, Behance) — pick what fits the role.\n"
    "- outreach_subject: a concise, non-spammy subject line.\n"
    "- outreach_message: a short, warm outreach draft (<120 words) with "
    "[placeholders] the recruiter fills in (e.g. [first name]). Never invent "
    "compensation or guarantees.\n"
    "Respond with a single JSON object using EXACTLY these keys: boolean_search "
    "(string), keywords (array of strings), platforms (array of strings), "
    "outreach_subject (string), outreach_message (string). Nothing else."
)


def generate_sourcing_kit(
    *,
    title: str,
    description: str | None = None,
    department: str | None = None,
    location: str | None = None,
    user_id: str | None = None,
) -> SourcingKit:
    """Generate a sourcing kit for a job via the chat gateway."""
    parts = [f"TITLE: {title}"]
    if department:
        parts.append(f"DEPARTMENT: {department}")
    if location:
        parts.append(f"LOCATION: {location}")
    parts.append(f"DESCRIPTION:\n{(description or '').strip() or '(none provided)'}")
    user_content = "\n".join(parts)

    try:
        result: SourcingKit = llm_call(
            profile="chat",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            schema=SourcingKit,
            user_id=user_id,
            metadata={"agent": "A2", "prompt_version": PROMPT_VERSION},
        )
    except ValidationError as exc:
        raise SourcingError(f"Sourcing output did not match SourcingKit schema: {exc}") from exc
    return result
