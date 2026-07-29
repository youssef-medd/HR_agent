"""A3 — CV ingestion & parsing.

Turns a raw CV (PDF / DOCX / plain text) into a validated `CVData` record.

Two stages:

1. `extract_text` — deterministic text extraction. PyMuPDF for PDF, python-docx
   for DOCX, passthrough for plain text/markdown. OCR (Tesseract) is a later
   fallback for scanned PDFs (ADR-006) and is intentionally not wired here yet.
2. `parse_cv` — sends the extracted text through the LLM gateway's `extractor`
   profile in JSON mode and validates the response into `CVData`. Deterministic
   (`temperature=0`, `seed=42`) so a persisted parse is reproducible from
   `(model, prompt_version, seed)`.

The masking of protected attributes (name, contact, dates …) required before
scoring (ADR-004) is A4's responsibility, not A1's — this stage extracts every
field faithfully.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

from app.gateway import llm_call
from pydantic import BaseModel, Field, ValidationError, field_validator

PROMPT_VERSION = "cv_parse@v2"
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


class CVParseError(RuntimeError):
    """Raised when no text can be extracted from the source document."""


# OCR fallback (spec §A3): when a PDF page's text layer is thinner than this,
# the page is likely a scan and is re-read with Tesseract. Off unless
# OCR_ENABLED is truthy and pytesseract + the tesseract binary are installed.
OCR_MIN_CHARS = 200


def _ocr_enabled() -> bool:
    return os.environ.get("OCR_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _needs_ocr(page_text: str) -> bool:
    return len(page_text.strip()) < OCR_MIN_CHARS


def _ocr_langs() -> str:
    return os.environ.get("OCR_LANGS", "fra+eng+ara")


def _apply_ocr_fallback(pages: list[str], ocr_provider) -> list[str]:
    """Replace thin (likely-scanned) pages with OCR text when enabled.

    `ocr_provider(index) -> str` renders + OCRs page `index`. Pure/​testable:
    the fitz rendering is injected, not imported here.
    """
    if not _ocr_enabled() or ocr_provider is None:
        return pages
    out: list[str] = []
    for i, text in enumerate(pages):
        if _needs_ocr(text):
            try:
                ocr_text = ocr_provider(i)
            except Exception:  # noqa: BLE001 - OCR is best-effort, never fatal
                ocr_text = ""
            out.append(ocr_text or text)
        else:
            out.append(text)
    return out


def _ocr_pdf_page(doc, index: int) -> str:
    """Render one PDF page to an image and OCR it (lazy, optional deps)."""
    import pytesseract  # optional; only present where OCR is provisioned

    page = doc[index]
    pix = page.get_pixmap(dpi=200)
    return pytesseract.image_to_string(pix.tobytes("png"), lang=_ocr_langs())


def extract_pages(filename: str, data: bytes) -> list[str]:
    """Extract text per page, dispatching on extension.

    PDF yields one entry per page (for source-page traceability); DOCX and
    plain text yield a single entry. Thin PDF pages fall back to OCR when
    OCR_ENABLED is set. Lazy-imports the heavy parsers.
    """
    name = filename.lower()

    if name.endswith(".pdf"):
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text() for page in doc]
            return _apply_ocr_fallback(pages, lambda i: _ocr_pdf_page(doc, i))
    elif name.endswith(".docx"):
        import io

        from docx import Document

        doc = Document(io.BytesIO(data))
        return ["\n".join(p.text for p in doc.paragraphs)]
    elif name.endswith((".txt", ".md")):
        return [data.decode("utf-8", errors="replace")]
    raise CVParseError(f"Unsupported CV file type: {filename!r}")


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from CV bytes (all pages joined)."""
    text = "\n".join(extract_pages(filename, data)).strip()
    if not text:
        raise CVParseError(f"No text extracted from {filename!r} (scanned PDF? OCR not wired yet)")
    return text


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


def _postprocess(cv: CVData, raw_text: str) -> CVData:
    """Deterministic post-processing: language + code-computed experience."""
    computed = compute_years_experience(cv.experiences)
    return cv.model_copy(update={
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
