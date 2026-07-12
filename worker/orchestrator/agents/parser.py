"""A1 — CV parser.

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

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.gateway import llm_call

PROMPT_VERSION = "cv_parse@v1"


class Experience(BaseModel):
    title: str = Field(default="", description="Job title / role")
    company: str = Field(default="", description="Employer name")
    start: str = Field(default="", description="Start date as written on the CV")
    end: str = Field(default="", description="End date, or 'present'")
    summary: str = Field(default="", description="One-line description of the role")


class Education(BaseModel):
    degree: str = Field(default="", description="Degree or qualification")
    institution: str = Field(default="", description="School / university name")
    year: str = Field(default="", description="Graduation year as written")


class CVData(BaseModel):
    """Structured CV. Every field is best-effort; missing data stays empty."""

    full_name: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    location: str = Field(default="")
    summary: str = Field(default="", description="Candidate's professional summary")
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    years_experience: float | None = Field(
        default=None, description="Total years of professional experience, best estimate"
    )
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    @field_validator("skills", "languages", mode="before")
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


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from CV bytes, dispatching on file extension.

    Lazy-imports the heavy parsers so a caller that only needs the LLM stage
    (or the test suite mocking it) does not pay the import cost.
    """
    name = filename.lower()

    if name.endswith(".pdf"):
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
    elif name.endswith(".docx"):
        import io

        from docx import Document

        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise CVParseError(f"Unsupported CV file type: {filename!r}")

    text = text.strip()
    if not text:
        raise CVParseError(f"No text extracted from {filename!r} (scanned PDF? OCR not wired yet)")
    return text


_SYSTEM_PROMPT = (
    "You are a precise CV parser. Extract the candidate's details from the CV text "
    "into the requested JSON schema. Rules:\n"
    "- full_name: the candidate's name, usually the most prominent line at the top.\n"
    "- experiences: include EVERY job/role listed, each with title, company, start, "
    "end and a one-line summary.\n"
    "- education: include EVERY qualification, with degree, institution and year.\n"
    "- years_experience: total years of professional experience. Use the number if "
    "the CV states it, otherwise estimate from the job date ranges; null only if "
    "there is no basis at all.\n"
    "- Copy values verbatim from the CV; never invent data. Leave a field empty "
    "(\"\" or []) only when the CV genuinely does not contain it.\n"
    "Respond with a single JSON object and nothing else."
)


def parse_cv(raw_text: str, *, user_id: str | None = None) -> CVData:
    """Extract structured `CVData` from already-extracted CV text via the gateway."""
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
            metadata={"agent": "A1", "prompt_version": PROMPT_VERSION},
        )
    except ValidationError as exc:
        # Schema drift from the model is a parse failure, not a crash — the node
        # routes the application to NEEDS_ATTENTION rather than retrying forever.
        raise CVParseError(f"LLM output did not match CVData schema: {exc}") from exc
    return result
