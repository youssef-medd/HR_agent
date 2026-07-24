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

PROMPT_VERSION = "sourcing@v2"


class OutreachDraft(BaseModel):
    tone: str = Field(default="", description="e.g. warm / direct / casual")
    subject: str = Field(default="")
    message: str = Field(default="", description="Personalisable draft with [placeholders]")


class SourcingKit(BaseModel):
    search_strings: list[str] = Field(
        default_factory=list,
        description="5-10 boolean/X-ray strings, ranked best-first",
    )
    keywords: list[str] = Field(
        default_factory=list, description="Core skills/titles to search on"
    )
    platforms: list[str] = Field(
        default_factory=list, description="Suggested sourcing platforms"
    )
    outreach: list[OutreachDraft] = Field(
        default_factory=list, description="Three outreach drafts in different tones"
    )


class SourcingError(RuntimeError):
    """Raised when the model output cannot be validated into a SourcingKit."""


_SYSTEM_PROMPT = (
    "You are an expert technical sourcer. Given a job posting, produce a practical "
    "sourcing kit a recruiter can act on immediately. Rules:\n"
    "- search_strings: 5 to 10 ready-to-paste boolean / Google X-ray strings "
    "(e.g. site:linkedin.com/in ...), ranked with the highest-precision first. "
    "Vary titles, synonyms, FR/EN variants and location filters.\n"
    "- keywords: the 6-12 most discriminating skills/titles for this role.\n"
    "- platforms: where these candidates are found (e.g. LinkedIn, GitHub, "
    "Stack Overflow, Kaggle, Behance) — pick what fits the role.\n"
    "- outreach: EXACTLY three drafts with distinct tones — 'warm', 'direct', "
    "'casual'. Each has a concise non-spammy subject and a short message "
    "(<120 words) using [placeholders] the recruiter fills in (e.g. [first name]). "
    "Never invent compensation or guarantees.\n"
    "Respond with a single JSON object using EXACTLY these keys: search_strings "
    "(array of strings), keywords (array of strings), platforms (array of "
    "strings), outreach (array of objects with keys tone, subject, message). "
    "Nothing else."
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
