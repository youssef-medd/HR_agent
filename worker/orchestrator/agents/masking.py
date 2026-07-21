"""Identity masking for the scoring judge (ADR-004).

The A4 judge must never see attributes that could bias it: name, contact
details, location, and institution proper names. `mask_cv` projects a `CVData`
onto a judge-safe dictionary containing only job-relevant signal.

The masking is the load-bearing part of the bias probe (ADR-005): two CVs that
differ only in identity fields produce byte-identical masked views, so an
identity swap cannot change the score.
"""

import re
from typing import Any

from orchestrator.agents.parser import CVData

# Dropped entirely (by omission below) — pure identity/contact, no bearing on
# fit: full_name, email, phone, location.

# Free-text fields (summaries) can still leak identity/contact and precise dates
# of birth. Scrub them (ADR-004): email addresses, and day-precision dates —
# which is where a DOB hides — are redacted, keeping only job-relevant signal.
# Year-only ranges like "2019-2024" have a single separator and are preserved so
# experience durations stay legible.
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_DAY_DATE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b")


def _scrub(text: str) -> str:
    if not text:
        return text
    text = _EMAIL.sub("[email]", text)
    text = _DAY_DATE.sub("[date]", text)
    return text


def mask_cv(cv: CVData) -> dict[str, Any]:
    """Project a parsed CV onto the identity-blind view the judge is allowed to see."""
    return {
        "summary": _scrub(cv.summary),
        "skills": list(cv.skills),
        "languages": list(cv.languages),
        "years_experience": cv.years_experience,
        "experiences": [
            {
                "title": e.title,
                "start": e.start,
                "end": e.end,
                "summary": _scrub(e.summary),
                # company kept: it describes the role context, not the candidate.
                "company": e.company,
            }
            for e in cv.experiences
        ],
        "education": [
            {
                "degree": e.degree,
                "year": e.year,
                # institution proper name is a sociocultural marker — redact it.
                "institution": "[institution]",
            }
            for e in cv.education
        ],
    }
