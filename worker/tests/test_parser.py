"""A1 CV parser tests — offline (the LLM gateway is monkeypatched).

Covers the deterministic text-extraction dispatch, the parse_cv gateway call,
and both parse_node branches (success stores CVData on the application; a
missing CV source routes the application to NEEDS_ATTENTION).
"""

from __future__ import annotations

import shutil

import pytest
from app.models.application import Application

from orchestrator.agents import parser as parser_mod
from orchestrator.agents.parser import CVData, CVParseError, extract_text, parse_cv


def test_cvdata_coerces_int_year_and_dates():
    # The LLM often returns year/dates as ints; the parser must coerce, not fail.
    cv = CVData.model_validate(
        {
            "full_name": "Amine",
            "education": [{"degree": "MSc", "institution": "INSAT", "year": 2019}],
            "experiences": [{"title": "Dev", "company": "Acme", "start": 2020, "end": 2024}],
        }
    )
    assert cv.education[0].year == "2019"
    assert cv.experiences[0].start == "2020" and cv.experiences[0].end == "2024"


def test_extract_text_plaintext_passthrough():
    assert extract_text("cv.txt", b"Jane Doe\nPython, SQL") == "Jane Doe\nPython, SQL"


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(CVParseError):
        extract_text("cv.rtf", b"whatever")


def test_extract_text_rejects_empty_document():
    with pytest.raises(CVParseError):
        extract_text("cv.txt", b"   \n  ")


def test_parse_cv_invokes_gateway_with_schema(monkeypatch):
    captured: dict = {}

    def fake_llm_call(*, profile, messages, schema, user_id=None, metadata=None, **_):
        captured.update(profile=profile, schema=schema, metadata=metadata)
        return CVData(full_name="Jane Doe", skills=["Python", "SQL"])

    monkeypatch.setattr(parser_mod, "llm_call", fake_llm_call)

    cv = parse_cv("Jane Doe — Python, SQL", user_id="42")

    assert isinstance(cv, CVData)
    assert cv.full_name == "Jane Doe"
    assert captured["profile"] == "extractor"
    assert captured["schema"] is CVData
    assert captured["metadata"]["agent"] == "A3"


def test_parse_cv_rejects_empty_text():
    with pytest.raises(CVParseError):
        parse_cv("   ")


def test_cvdata_flattens_language_objects():
    # The model sometimes returns {"name": ..., "proficiency": ...} per language.
    cv = CVData.model_validate(
        {
            "full_name": "X",
            "languages": [{"name": "Arabic", "proficiency": "Native"}, "English"],
            "skills": [{"skill": "Python"}, "SQL"],
        }
    )
    assert cv.languages == ["Arabic", "English"]
    assert cv.skills == ["Python", "SQL"]


def test_parse_cv_wraps_schema_drift_as_parse_error(monkeypatch):
    # Simulate the gateway raising a pydantic ValidationError on model output.
    def boom(**_):
        return CVData.model_validate({"experiences": "not-a-list"})

    monkeypatch.setattr(parser_mod, "llm_call", boom)
    with pytest.raises(CVParseError):
        parse_cv("some cv text")


def test_extract_pages_plaintext_single_page():
    from orchestrator.agents.parser import extract_pages

    assert extract_pages("cv.txt", b"line1\nline2") == ["line1\nline2"]


def test_ocr_fallback_disabled_by_default(monkeypatch):
    from app.textract import apply_ocr_fallback as _apply_ocr_fallback

    monkeypatch.delenv("OCR_ENABLED", raising=False)
    pages = ["", "short"]  # both thin
    called = []
    out = _apply_ocr_fallback(pages, lambda i: called.append(i) or "OCR")
    assert out == pages and called == []  # provider never invoked


def test_ocr_fallback_replaces_thin_pages_when_enabled(monkeypatch):
    from app.textract import apply_ocr_fallback as _apply_ocr_fallback

    monkeypatch.setenv("OCR_ENABLED", "1")
    thick = "x" * 300
    pages = [thick, "scanned-thin-page"]
    out = _apply_ocr_fallback(pages, lambda i: f"OCR{i}")
    assert out[0] == thick          # thick page left as-is
    assert out[1] == "OCR1"          # thin page replaced by OCR


def test_needs_ocr_threshold():
    from app.textract import needs_ocr as _needs_ocr

    assert _needs_ocr("x" * 199) is True
    assert _needs_ocr("x" * 200) is False


def test_image_cv_without_ocr_reports_ocr_not_unsupported(monkeypatch):
    """An image CV is a supported type — the failure must name OCR, so the
    recruiter is told to provision it rather than that the file is wrong."""
    from orchestrator.agents.parser import CVParseError, extract_pages

    monkeypatch.delenv("OCR_ENABLED", raising=False)
    with pytest.raises(CVParseError, match="OCR"):
        extract_pages("cv.png", b"\x89PNG\r\n\x1a\n")


def test_image_cv_is_ocred_when_enabled(monkeypatch):
    from orchestrator.agents.parser import extract_pages

    monkeypatch.setenv("OCR_ENABLED", "1")
    monkeypatch.setattr(
        "app.textract.ocr_image_bytes", lambda data: "Mohamed Ali\nPython"
    )
    assert extract_pages("cv.jpg", b"jpeg-bytes") == ["Mohamed Ali\nPython"]


def test_ocr_failure_surfaces_as_parse_error(monkeypatch):
    from orchestrator.agents.parser import CVParseError, extract_pages

    monkeypatch.setenv("OCR_ENABLED", "1")

    def _boom(data):
        raise OSError("cannot identify image file")

    monkeypatch.setattr("app.textract.ocr_image_bytes", _boom)
    with pytest.raises(CVParseError, match="OCR failed"):
        extract_pages("cv.png", b"not-an-image")


def test_unknown_extension_still_rejected():
    from orchestrator.agents.parser import CVParseError, extract_pages

    with pytest.raises(CVParseError, match="Unsupported"):
        extract_pages("cv.xlsx", b"whatever")


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not provisioned"
)
def test_scanned_pdf_is_ocred_end_to_end(monkeypatch):
    """A PDF whose pages are pure images (no text layer) is recovered via OCR.

    Guards the real integration — the mocked tests above would still pass if
    tesseract were missing or the language packs were wrong.
    """
    import pymupdf
    from app.textract import extract_pages
    from app.textract import needs_ocr as _needs_ocr

    monkeypatch.setenv("OCR_ENABLED", "1")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Mohamed Ali", fontsize=20)
    page.insert_text((72, 130), "Software Engineer", fontsize=14)
    image = page.get_pixmap(dpi=200).tobytes("png")

    scan = pymupdf.open()
    scanned_page = scan.new_page()
    scanned_page.insert_image(scanned_page.rect, stream=image)
    data = scan.tobytes()

    # Precondition: the wrapped PDF really has no text layer.
    assert _needs_ocr(pymupdf.open(stream=data, filetype="pdf")[0].get_text())

    text = extract_pages("scan.pdf", data)[0]
    assert "Mohamed Ali" in text
    assert "Software Engineer" in text


def test_attach_sources_tags_page_and_snippet():
    from orchestrator.agents.parser import CVData, Experience, attach_sources

    pages = [
        "Header page with a summary and skills.",
        "Experience\nSoftware Engineer at Acme Corp 2019-2022 building APIs.",
    ]
    cv = CVData(experiences=[
        Experience(title="Software Engineer", company="Acme Corp", start="2019", end="2022"),
        Experience(title="Ghost", company="Nowhere Inc"),  # not in any page
    ])
    tagged = attach_sources(cv, pages)
    assert tagged.experiences[0].source_page == 2
    assert "acme corp" in tagged.experiences[0].source_snippet
    assert tagged.experiences[1].source_page is None  # no match -> empty


def test_compute_years_experience_from_date_ranges():
    from orchestrator.agents.parser import Experience, compute_years_experience

    exps = [
        Experience(title="A", start="2018", end="2021"),   # 3
        Experience(title="B", start="2021", end="present"),  # to now
        Experience(title="C", start="bad", end="also-bad"),  # ignored
    ]
    total = compute_years_experience(exps)
    assert total is not None and total >= 3
    # No parseable dates -> None
    assert compute_years_experience([Experience(title="X")]) is None


def test_compute_years_clamps_reversed_dates():
    from orchestrator.agents.parser import Experience, compute_years_experience

    # end before start -> 0, not negative
    assert compute_years_experience([Experience(start="2022", end="2019")]) == 0.0


def test_detect_language_en_fr():
    from orchestrator.agents.parser import detect_language

    assert detect_language("This is an English CV about backend engineering and cloud.") == "en"
    assert detect_language("Ceci est un CV en français pour un poste d'ingénieur backend.") == "fr"
    assert detect_language("short") == ""  # too short to detect


def test_parse_cv_computes_experience_and_language(monkeypatch):
    # The LLM's years_experience guess is overridden by the code computation.
    def fake(*, profile, messages, schema, **_):
        return CVData(
            full_name="Jane", years_experience=99.0,
            experiences=[parser_mod.Experience(title="Dev", start="2019", end="2022")],
        )

    monkeypatch.setattr(parser_mod, "llm_call", fake)
    cv = parse_cv("A reasonably long English CV text for language detection to work well.")
    assert cv.years_experience == 3.0  # computed, not 99
    assert cv.language == "en"


def test_parse_cv_repairs_on_first_failure(monkeypatch):
    # extractor raises schema drift -> repair pass (judge) succeeds.
    calls: list[str] = []

    def fake(*, profile, messages, schema, **_):
        calls.append(profile)
        if profile == "extractor":
            return CVData.model_validate({"experiences": "not-a-list"})  # ValidationError
        return CVData(full_name="Repaired")

    monkeypatch.setattr(parser_mod, "llm_call", fake)
    cv = parse_cv("some cv text long enough to detect language properly here")
    assert cv.full_name == "Repaired"
    assert calls == ["extractor", "judge"]


def _seed_app(db_factory, payload: dict) -> int:
    with db_factory() as db:
        row = Application(job_id=1, candidate_ref="a@b.c", state="RECEIVED", payload=payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def test_parse_node_stores_cv_and_advances(db_factory, monkeypatch):
    from orchestrator import nodes

    monkeypatch.setattr(
        nodes, "parse_cv", lambda text, **_: CVData(full_name="Jane Doe", skills=["Python"])
    )
    app_id = _seed_app(db_factory, {"cv_text": "Jane Doe, Python developer"})

    with db_factory() as db:
        state = nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    assert state["stage"] == "PARSED"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "PARSED"
        assert row.payload["cv"]["full_name"] == "Jane Doe"
        # Traceability (spec §A3): raw_text + parser_version retained.
        assert row.payload["raw_text"] == "Jane Doe, Python developer"
        assert row.payload["parser_version"] == parser_mod.PARSER_VERSION
        assert "language" in row.payload


def test_parse_node_prefers_the_name_the_applicant_typed(db_factory, monkeypatch):
    """The apply form prefills the name from the CV and lets the candidate fix
    it; that correction is what the recruiter must see."""
    from orchestrator import nodes

    monkeypatch.setattr(
        nodes, "parse_cv", lambda text, **_: CVData(full_name="JANE D0E", skills=["Python"])
    )
    app_id = _seed_app(
        db_factory, {"cv_text": "JANE D0E, Python developer", "applicant_name": "Jane Doe"}
    )

    with db_factory() as db:
        nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    with db_factory() as db:
        cv = db.get(Application, app_id).payload["cv"]
        assert cv["full_name"] == "Jane Doe"
        # The parser's own reading stays on record.
        assert cv["parsed_full_name"] == "JANE D0E"


def test_parse_node_keeps_the_parsed_name_when_the_form_adds_nothing(db_factory, monkeypatch):
    from orchestrator import nodes

    monkeypatch.setattr(
        nodes, "parse_cv", lambda text, **_: CVData(full_name="Jane Doe", skills=["Python"])
    )
    app_id = _seed_app(db_factory, {"cv_text": "Jane Doe", "applicant_name": ""})

    with db_factory() as db:
        nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    with db_factory() as db:
        cv = db.get(Application, app_id).payload["cv"]
        assert cv["full_name"] == "Jane Doe"
        assert "parsed_full_name" not in cv


def test_parse_node_routes_to_needs_attention_without_cv(db_factory):
    from orchestrator import nodes

    app_id = _seed_app(db_factory, {})  # no cv_text / cv_b64 / cv_path

    with db_factory() as db:
        state = nodes.parse_node(db, {"application_id": app_id, "stage": "RECEIVED", "attempt": 1})

    assert state["stage"] == "NEEDS_ATTENTION"
    with db_factory() as db:
        row = db.get(Application, app_id)
        assert row.state == "NEEDS_ATTENTION"


def test_docx_reads_content_inside_tables():
    """A CV laid out in tables must not extract as an empty document.

    `document.paragraphs` alone returns almost nothing for these templates —
    the reference corpus file `07_tables_layout.docx` dropped from 1388 chars
    to 59 before this was handled.
    """
    import io

    from app.textract import extract_text
    from docx import Document

    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "2020 - present"
    table.cell(0, 1).text = "Chef de projet senior, Vermeg"
    buf = io.BytesIO()
    doc.save(buf)

    text = extract_text("cv.docx", buf.getvalue())
    assert "Vermeg" in text
    # Date and job stay on one line, so the date is not orphaned from its role.
    assert "2020 - present\tChef de projet senior, Vermeg" in text


def test_arabic_presentation_forms_are_normalised():
    """Arabic PDFs store shaped glyphs that compare unequal to canonical letters."""
    from app.textract import normalize_extracted

    assert normalize_extracted("ﻳﺎﺳﻴﻦ ﺍﻟﻄﺮﺍﺑﻞﺴﻲ") == "ياسين الطرابلسي"


def test_obfuscated_contacts_are_normalised():
    """Candidates hide contacts from scrapers; the model copies what it sees."""
    from orchestrator.agents.parser import normalize_email, normalize_name, normalize_phone

    assert normalize_email("sofiane . zouari (at) yahoo . fr") == "sofiane.zouari@yahoo.fr"
    # A URL is not an address — `09_missing_email.pdf` expects nothing here.
    assert normalize_email("github.com/mgharbi-ops") == ""
    assert normalize_phone("21 6 - 92 - 664 - 105") == "+21692664105"
    assert normalize_phone("00216 55 302 887") == "+21655302887"
    assert normalize_phone("55 214 803") == "55214803"  # local, no country code
    assert normalize_name("S O F I A N E   Z O U A R I") == "SOFIANE ZOUARI"
    assert normalize_name("Omar Ben Salah") == "Omar Ben Salah"
