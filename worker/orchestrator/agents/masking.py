"""Identity masking for the scoring judge (ADR-004).

The A4 judge must never see attributes that could bias it: name, contact
details, location, and institution proper names. `mask_cv` projects a `CVData`
onto a judge-safe dictionary containing only job-relevant signal.

The masking is the load-bearing part of the bias probe (ADR-005): two CVs that
differ only in identity fields produce byte-identical masked views, so an
identity swap cannot change the score.
"""

from __future__ import annotations

from typing import Any

from orchestrator.agents.parser import CVData

# Dropped entirely (by omission below) — pure identity/contact, no bearing on
# fit: full_name, email, phone, location.


def mask_cv(cv: CVData) -> dict[str, Any]:
    """Project a parsed CV onto the identity-blind view the judge is allowed to see."""
    return {
        "summary": cv.summary,
        "skills": list(cv.skills),
        "languages": list(cv.languages),
        "years_experience": cv.years_experience,
        "experiences": [
            {
                "title": e.title,
                "start": e.start,
                "end": e.end,
                "summary": e.summary,
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
