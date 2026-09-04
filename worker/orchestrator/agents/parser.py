"""A3 — CV ingestion & parsing.

Turns a raw CV (PDF / DOCX / image / plain text) into a validated `CVData`
record.

Two stages:

1. `extract_text` — deterministic text extraction. PyMuPDF for PDF, python-docx
   for DOCX, passthrough for plain text/markdown. A PDF page whose text layer is
   thinner than `OCR_MIN_CHARS` is treated as a scan and re-read with Tesseract
   (ADR-006); an image CV has no text layer at all and goes straight to OCR.
   Both need `OCR_ENABLED` plus a provisioned `tesseract` binary.
2. `parse_cv` — sends the extracted text through the LLM gateway's `extractor`
   profile in JSON mode and validates the response into `CVData`. Deterministic
   (`temperature=0`, `seed=42`) so a persisted parse is reproducible from
   `(model, prompt_version, seed)`.

The masking of protected attributes (name, contact, dates …) required before
scoring (ADR-004) is A4's responsibility, not A1's — this stage extracts every
field faithfully.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.gateway import llm_call
from app.textract import (
    IMAGE_EXT as _IMAGE_EXT,
)
from app.textract import (
    OCR_MIN_CHARS as _OCR_MIN_CHARS,
)
from app.textract import (
    TextExtractionError,
    extract_pages,
    extract_text,
)
from pydantic import BaseModel, Field, ValidationError, field_validator

PROMPT_VERSION = "cv_parse@v3"
# Bumped when extraction/post-processing logic changes; stored with each parse
# so a persisted profile is reproducible from (model, prompt_version, parser).
PARSER_VERSION = "a3-parser@v2"


def _coerce_str(v: object) -> object:
    """Cast scalars the model may emit as int/float (e.g. a year 2019) to str.

    Date and year fields are declared as strings, but the LLM frequently returns
    a bare integer for them; coerce rather than fail validation.
    """
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    return v


class Experience(BaseModel):
    title: str = Field(default="", description="Job title / role")
    company: str = Field(default="", description="Employer name")
    start: str = Field(default="", description="Start date as written on the CV")
    end: str = Field(default="", description="End date, or 'present'")
    summary: str = Field(default="", description="One-line description of the role")
    # Traceability to the source document (spec §A3): the page and a short
    # verbatim snippet supporting this entry, used for A4 evidence links.
    source_page: int | None = Field(default=None)
    source_snippet: str = Field(default="")

    @field_validator("start", "end", mode="before")
    @classmethod
    def _coerce_dates(cls, v: object) -> object:
        return _coerce_str(v)


class Education(BaseModel):
    degree: str = Field(default="", description="Degree or qualification")
    institution: str = Field(default="", description="School / university name")
    year: str = Field(default="", description="Graduation year as written")

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v: object) -> object:
        return _coerce_str(v)


class CVData(BaseModel):
    """Structured CV. Every field is best-effort; missing data stays empty."""

    full_name: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    location: str = Field(default="")
    links: list[str] = Field(default_factory=list, description="Profile/portfolio URLs")
    summary: str = Field(default="", description="Candidate's professional summary")
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    years_experience: float | None = Field(
        default=None, description="Total years of professional experience, best estimate"
    )
    # Document language (ISO 639-1), detected in code — not the spoken `languages`.
    language: str = Field(default="")
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    @field_validator("skills", "languages", "certifications", "links", mode="before")
    @classmethod
    def _flatten_str_list(cls, v: object) -> object:
        """Coerce list-of-objects to list-of-strings.

        The model sometimes returns e.g. ``{"name": "Arabic", "proficiency":
        "Native"}`` for a language. Flatten each item to a bare string so the
        richer shape does not fail validation.
        """
        if not isinstance(v, list):
            return v
        out: list[str] = []
        for item in v:
            if isinstance(item, dict):
                value = (
                    item.get("name")
                    or item.get("language")
                    or item.get("skill")
                    or item.get("value")
                    or next((x for x in item.values() if isinstance(x, str)), "")
                )
                out.append(str(value))
            elif item is not None:
                out.append(str(item))
        return out


# A3's error type IS the shared extraction error, so `except CVParseError`
# keeps catching extraction failures after the move to `app.textract`.
CVParseError = TextExtractionError


# Text extraction lives in `app.textract` — the API needs the same code to
# pre-fill the application form from a dropped CV, so it cannot live in the
# worker package. Re-exported here because `extract_pages` / `extract_text` /
# `OCR_MIN_CHARS` are A3's documented surface.
OCR_MIN_CHARS = _OCR_MIN_CHARS
IMAGE_EXT = _IMAGE_EXT

__all__ = [
    "CVData",
    "CVParseError",
    "Education",
    "Experience",
    "IMAGE_EXT",
    "OCR_MIN_CHARS",
    "PARSER_VERSION",
    "PROMPT_VERSION",
    "attach_sources",
    "compute_years_experience",
    "detect_language",
    "extract_pages",
    "extract_text",
    "parse_cv",
]


def attach_sources(cv: CVData, pages: list[str]) -> CVData:
    """Tag each experience with the source page + snippet it was drawn from.

    Locates the first page whose text mentions the role's company (or title)
    and captures a short window around it. Best-effort: entries with no match
    keep empty source fields.
    """
    if not pages:
        return cv
    norm_pages = [(" ".join(p.split())).lower() for p in pages]
    updated: list[Experience] = []
    for exp in cv.experiences:
        needle = (exp.company or exp.title or "").strip().lower()
        page_no: int | None = None
        snippet = ""
        if needle:
            for i, page in enumerate(norm_pages):
                pos = page.find(needle)
                if pos != -1:
                    page_no = i + 1  # 1-based
                    start = max(0, pos - 40)
                    snippet = page[start : pos + len(needle) + 80].strip()
                    break
        updated.append(exp.model_copy(update={"source_page": page_no, "source_snippet": snippet}))
    return cv.model_copy(update={"experiences": updated})


_SYSTEM_PROMPT = (
    "You are a precise CV parser. Extract the candidate's details from the CV text "
    "into the requested JSON schema. Rules:\n"
    "- full_name: the candidate's name, usually the most prominent line at the top.\n"
    "- email / phone: the candidate's contact details. ALWAYS extract these when "
    "present — they are often on one header line next to each other, or beside an "
    "icon. Keep the phone exactly as written, including its country code. These "
    "identify the candidate across applications, so never skip them.\n"
    "- location: the candidate's city / country, if stated.\n"
    "- links: any profile/portfolio URLs (LinkedIn, GitHub, personal site).\n"
    "- skills: aggregate ALL technologies, tools, frameworks and languages mentioned "
    "anywhere in the CV — including tech stacks listed inside project or experience "
    "entries — deduplicated. Do not require a dedicated 'Skills' section.\n"
    "- certifications: professional certifications / licences, if any.\n"
    "- experiences: include EVERY job/role listed, each with title, company, start, "
    "end and a one-line summary.\n"
    "- education: include EVERY qualification, with degree, institution and year.\n"
    "- years_experience: leave your best estimate; it is recomputed in code from the "
    "experience date ranges.\n"
    "- Copy values verbatim from the CV; never invent data. Leave a field empty "
    "(\"\" or []) only when the CV genuinely does not contain it.\n"
    "Respond with a single JSON object and nothing else."
)


def detect_language(text: str) -> str:
    """ISO 639-1 language of the CV text (e.g. 'fr'/'en'/'ar'), '' if undetectable."""
    sample = text.strip()
    if len(sample) < 20:
        return ""
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0  # deterministic
        return detect(sample)
    except Exception:  # noqa: BLE001 - langdetect raises on empty/ambiguous input
        return ""


_YEAR_RE = re.compile(r"(19|20)\d{2}")
_PRESENT_RE = re.compile(r"present|current|now|actuel|aujourd|présent", re.IGNORECASE)


def _year_of(value: str, *, end: bool = False) -> int | None:
    """Best-effort 4-digit year from a free-text date; 'present' -> current year."""
    if not value:
        return None
    if end and _PRESENT_RE.search(value):
        return datetime.now(UTC).year
    m = _YEAR_RE.search(value)
    return int(m.group(0)) if m else None


def compute_years_experience(experiences: list[Experience]) -> float | None:
    """Total professional experience in years, computed in code (spec §A3).

    Sums each role's (end_year - start_year); a role with an end before its start
    is clamped to 0 (date-consistency guard). Returns None when no role has a
    parseable date range.
    """
    total = 0.0
    seen = False
    for exp in experiences:
        start = _year_of(exp.start)
        end = _year_of(exp.end, end=True)
        if start is None:
            continue
        seen = True
        if end is None:
            end = datetime.now(UTC).year
        total += max(0, end - start)
    return round(total, 1) if seen else None


# Candidates obfuscate contact details to dodge scrapers — "(at)" for @, spaced
# dots, digits broken up. The model copies what it sees (correctly: it must not
# invent), so the un-mangling belongs here, in code.
_AT_FORMS = re.compile(r"\s*(?:\(\s*at\s*\)|\[\s*at\s*\]|\s+at\s+)\s*", re.IGNORECASE)
_DOT_FORMS = re.compile(r"\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\s+dot\s+)\s*", re.IGNORECASE)


def normalize_email(value: str) -> str:
    """Un-obfuscate an email. Returns "" when the result is not a valid address."""
    text = (value or "").strip()
    if not text:
        return ""
    text = _AT_FORMS.sub("@", text)
    text = _DOT_FORMS.sub(".", text)
    text = re.sub(r"\s*\.\s*", ".", text)  # "yahoo . fr" -> "yahoo.fr"
    text = text.replace(" ", "")
    return text.lower() if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text) else ""


def normalize_phone(value: str) -> str:
    """Collapse a phone number written with stray spaces/dashes.

    "21 6 - 92 - 664 - 105" and "00216 55 302 887" both survive as a usable
    number; anything without a plausible digit count is dropped rather than
    stored as junk.
    """
    text = (value or "").strip()
    digits = re.sub(r"\D", "", text)
    if not 8 <= len(digits) <= 15:
        return ""
    if text.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    # A local number is 8 digits here; anything longer already carries a country
    # code, so restore the "+" the candidate dropped ("216 92 664 105").
    return "+" + digits if len(digits) > 10 else digits


def normalize_name(value: str) -> str:
    """Collapse a letter-spaced name: 'S O F I A N E  Z O U A R I'.

    Detected rather than assumed: only collapsed when nearly every whitespace-
    separated token is a single character, which prose never is.
    """
    text = (value or "").strip()
    if not text:
        return ""
    # Split on the wide gaps FIRST — in a letter-spaced name the double space is
    # the only surviving word boundary, and collapsing whitespace destroys it.
    words = re.split(r"\s{2,}", text)
    tokens = text.split()
    singles = sum(1 for t in tokens if len(t) == 1)
    if len(tokens) >= 4 and singles >= len(tokens) - 1:
        return " ".join("".join(w.split()) for w in words if w.strip())
    return " ".join(tokens)


def _postprocess(cv: CVData, raw_text: str) -> CVData:
    """Deterministic post-processing: contacts, language, computed experience."""
    computed = compute_years_experience(cv.experiences)
    return cv.model_copy(update={
        "full_name": normalize_name(cv.full_name),
        "email": normalize_email(cv.email),
        "phone": normalize_phone(cv.phone) or cv.phone,
        "language": detect_language(raw_text),
        "years_experience": computed if computed is not None else cv.years_experience,
    })


_REPAIR_PROMPT = (
    "The following text is a failed attempt to produce a CV JSON object. Fix it so "
    "it is a single valid JSON object matching the required schema (identity, "
    "contact, links, summary, skills, languages, certifications, experiences, "
    "education). Keep all real data; drop anything that does not fit. Respond with "
    "the corrected JSON object and nothing else."
)


def parse_cv(raw_text: str, *, user_id: str | None = None) -> CVData:
    """Extract structured `CVData` from already-extracted CV text via the gateway.

    Fast path uses the 8B `extractor`. On schema drift a single repair pass runs
    through the stronger `judge` model (spec §A3 "70B repair pass") before giving
    up. Language and total experience are then computed in code.
    """
    if not raw_text.strip():
        raise CVParseError("Empty CV text passed to parse_cv")

    try:
        result: CVData = llm_call(
            profile="extractor",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            schema=CVData,
            user_id=user_id,
            metadata={"agent": "A3", "prompt_version": PROMPT_VERSION, "stage": "extract"},
        )
    except ValidationError:
        result = _repair_parse(raw_text, user_id=user_id)

    return _postprocess(result, raw_text)


def _repair_parse(raw_text: str, *, user_id: str | None = None) -> CVData:
    """Second-chance extraction through the stronger judge model."""
    try:
        return llm_call(
            profile="judge",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT + "\n\n" + _REPAIR_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            schema=CVData,
            user_id=user_id,
            metadata={"agent": "A3", "prompt_version": PROMPT_VERSION, "stage": "repair"},
        )
    except ValidationError as exc:
        # Both passes failed — a parse failure, not a crash. The node routes the
        # application to NEEDS_ATTENTION rather than retrying forever.
        raise CVParseError(f"LLM output did not match CVData schema: {exc}") from exc
