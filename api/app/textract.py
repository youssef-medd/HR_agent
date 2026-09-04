"""Document text extraction — shared by A3 (worker) and the apply form (API).

Lives in `app.*` for the same reason `app.embedding` and `app.portal_token` do:
both processes need it. The worker parses CVs here after submission; the API
uses it to pre-fill the application form the moment a candidate drops their CV.

PyMuPDF for PDF, python-docx for DOCX, passthrough for plain text. A PDF page
whose text layer is thinner than `OCR_MIN_CHARS` is treated as a scan and
re-read with Tesseract; an image has no text layer at all and goes straight to
OCR. Both need `OCR_ENABLED` plus a provisioned `tesseract` binary.
"""

from __future__ import annotations

import os
import unicodedata

# When a PDF page's text layer is thinner than this, the page is likely a scan
# and is re-read with Tesseract (spec §A3).
OCR_MIN_CHARS = 200

# Image CVs (a photo or a scan) carry no text layer at all, so OCR is the only
# route — there is no thin-text threshold to check first.
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


class TextExtractionError(RuntimeError):
    """Raised when no text can be extracted from the source document."""


def ocr_enabled() -> bool:
    return os.environ.get("OCR_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def needs_ocr(page_text: str) -> bool:
    return len(page_text.strip()) < OCR_MIN_CHARS


def ocr_langs() -> str:
    return os.environ.get("OCR_LANGS", "fra+eng+ara")


def ocr_image_bytes(data: bytes) -> str:
    """OCR raw image bytes. Lazy-imports the optional OCR stack."""
    import io

    import pytesseract  # optional; only present where OCR is provisioned
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return pytesseract.image_to_string(img, lang=ocr_langs())


def apply_ocr_fallback(pages: list[str], ocr_provider) -> list[str]:
    """Replace thin (likely-scanned) pages with OCR text when enabled.

    `ocr_provider(index) -> str` renders + OCRs page `index`. Pure/testable: the
    rendering is injected, not imported here.
    """
    if not ocr_enabled() or ocr_provider is None:
        return pages
    out: list[str] = []
    for i, text in enumerate(pages):
        if needs_ocr(text):
            try:
                ocr_text = ocr_provider(i)
            except Exception:  # noqa: BLE001 - OCR is best-effort, never fatal
                ocr_text = ""
            out.append(ocr_text or text)
        else:
            out.append(text)
    return out


def _ocr_pdf_page(doc, index: int) -> str:
    """Render one PDF page to an image and OCR it."""
    page = doc[index]
    pix = page.get_pixmap(dpi=200)
    return ocr_image_bytes(pix.tobytes("png"))


def _docx_blocks(parent) -> list[str]:
    """Text of a DOCX body in reading order, descending into tables.

    `document.paragraphs` walks only top-level paragraphs, so a CV laid out in
    tables — a common template style — extracts as almost nothing. Cells are
    walked recursively because a skills matrix is often a table nested inside a
    cell of the outer layout table.

    Cells on a row are joined with a tab so a date column stays on the same line
    as the job it belongs to, rather than floating away as an orphan line.
    """
    from docx.document import Document as _Doc
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    element = parent.element.body if isinstance(parent, _Doc) else parent._tc
    out: list[str] = []
    for child in element.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = Paragraph(child, parent).text.strip()
            if text:
                out.append(text)
        elif tag == "tbl":
            for row in Table(child, parent).rows:
                cells = [" ".join(_docx_blocks(c)).strip() for c in row.cells]
                line = "\t".join(c for c in cells if c).strip()
                if line:
                    out.append(line)
    return out


def extract_pages(filename: str, data: bytes) -> list[str]:
    """Extract text per page, dispatching on extension.

    PDF yields one entry per page (for source-page traceability); DOCX, images
    and plain text yield a single entry.
    """
    name = filename.lower()

    if name.endswith(".pdf"):
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text() for page in doc]
            return apply_ocr_fallback(pages, lambda i: _ocr_pdf_page(doc, i))
    elif name.endswith(IMAGE_EXT):
        if not ocr_enabled():
            raise TextExtractionError(
                f"{filename!r} is an image CV but OCR is disabled (set OCR_ENABLED=1)"
            )
        try:
            return [ocr_image_bytes(data)]
        except TextExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as an extraction failure
            raise TextExtractionError(f"OCR failed for {filename!r}: {exc}") from exc
    elif name.endswith(".docx"):
        import io

        from docx import Document

        return ["\n".join(_docx_blocks(Document(io.BytesIO(data))))]
    elif name.endswith((".txt", ".md")):
        return [data.decode("utf-8", errors="replace")]
    raise TextExtractionError(f"Unsupported CV file type: {filename!r}")


def normalize_extracted(text: str) -> str:
    """Unicode-normalise extracted text (NFKC).

    Arabic PDFs frequently store glyphs from the Arabic Presentation Forms-B
    block (U+FE70–U+FEFF) — the shaped, position-specific forms — rather than
    canonical letters. They look identical but compare unequal, so a name reads
    as 'ﻳﺎﺳﻴﻦ' instead of 'ياسين' and every downstream match fails. NFKC folds
    them back, and also tidies Latin ligatures and full-width characters.
    """
    return unicodedata.normalize("NFKC", text)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from document bytes (all pages joined)."""
    text = normalize_extracted("\n".join(extract_pages(filename, data))).strip()
    if not text:
        raise TextExtractionError(
            f"No text extracted from {filename!r} "
            f"(scanned document? check OCR_ENABLED and the tesseract install)"
        )
    return text
