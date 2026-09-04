"""Pre-fill the application form from a dropped CV.

Runs the moment a candidate attaches their file, before they submit, so they do
not retype what the CV already says. This is *not* A3 — A3 does the full
structured parse after submission. This is a fast, cheap read of the contact
block only.

Contact details are pulled with regexes rather than a model: an email, a phone
number and a LinkedIn URL have exact shapes, so a regex is both more reliable
and instant. Only the name needs a model, because "the candidate's name" has no
syntax — and even that is capped to the top of the document, where names live.

Everything is best-effort. A field we cannot read comes back empty and the
candidate types it themselves; nothing here can block an application.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.gateway import llm_call

PROMPT_VERSION = "cv_prefill@v1"

# Only the header is searched for contact details — a phone number quoted inside
# a job description should not become the candidate's number.
_HEADER_CHARS = 1200

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
# International or local, with spaces/dots/dashes: +216 98 447 210, 0612345678.
_PHONE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}")
_LINKEDIN = re.compile(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/[\w%-]+/?", re.I)
_URL = re.compile(r"https?://[^\s<>\"')]+|(?:www\.)[^\s<>\"')]+", re.I)


class CVPrefill(BaseModel):
    full_name: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    link: str = Field(default="")


class _NameOnly(BaseModel):
    full_name: str = Field(default="")


_NAME_SYSTEM = (
    "You are given the top of a CV. Return ONLY the candidate's own full name, "
    "exactly as written, in the document's own script (do not transliterate). "
    "It is usually the most prominent line at the very top. Never return a job "
    "title, a company, a university, a section heading, or an email address. If "
    "there is no clear personal name, return an empty string. Respond with a "
    'single JSON object {"full_name": "..."}. Nothing else.'
)


def _clean_phone(raw: str) -> str:
    """Keep a candidate-looking phone, or discard it.

    The loose pattern also matches date ranges ("2018 2021") and long ID
    numbers, so require a plausible digit count.
    """
    digits = re.sub(r"\D", "", raw)
    if not 8 <= len(digits) <= 15:
        return ""
    return " ".join(raw.split())


def extract_contacts(text: str) -> CVPrefill:
    """Regex-only pass. Deterministic, instant, no tokens spent."""
    header = text[:_HEADER_CHARS]

    email = ""
    match = _EMAIL.search(header) or _EMAIL.search(text)
    if match:
        email = match.group(0)

    phone = ""
    for candidate in _PHONE.finditer(header):
        # Skip anything that is part of the email we already took.
        if email and candidate.group(0).strip() in email:
            continue
        cleaned = _clean_phone(candidate.group(0))
        if cleaned:
            phone = cleaned
            break

    link = ""
    li = _LINKEDIN.search(text)
    if li:
        raw = li.group(0)
        link = raw if raw.lower().startswith("http") else f"https://{raw}"
    else:
        # No LinkedIn — fall back to the first URL that is not an email domain.
        for url in _URL.finditer(header):
            found = url.group(0).rstrip(".,;)")
            if "@" in found:
                continue
            link = found if found.lower().startswith("http") else f"https://{found}"
            break

    return CVPrefill(email=email, phone=phone, link=link)


def extract_name(text: str, *, user_id: str | None = None) -> str:
    """Read the candidate's name from the head of the CV. "" on any failure."""
    header = text[:600].strip()
    if not header:
        return ""
    try:
        result: _NameOnly = llm_call(
            profile="extractor",
            messages=[
                {"role": "system", "content": _NAME_SYSTEM},
                {"role": "user", "content": header},
            ],
            schema=_NameOnly,
            user_id=user_id,
            metadata={"agent": "A3", "prompt_version": PROMPT_VERSION, "stage": "prefill"},
        )
    except Exception:  # noqa: BLE001 — prefill is a convenience, never a blocker
        return ""

    name = result.full_name.strip()
    # A model that echoes the email or a heading is worse than an empty field.
    if "@" in name or len(name) > 80:
        return ""
    return name


def prefill_from_text(text: str, *, user_id: str | None = None) -> CVPrefill:
    """Contact details by regex, name by model."""
    prefill = extract_contacts(text)
    return prefill.model_copy(update={"full_name": extract_name(text, user_id=user_id)})
