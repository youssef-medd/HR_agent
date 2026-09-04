# CV parser test set

13 fake CVs covering the failure modes a résumé parser actually hits. Every person,
company, email and phone number here is invented — safe to commit to a repo.

`manifest.json` holds the ground truth for each file (expected name, email, phone,
employers, skills, languages…) plus the specific behaviour each file is meant to test.

## Files

| File | Covers | Language | Pages | OCR needed |
|---|---|---|---|---|
| `01_en_normal.pdf` | normal PDF, English | EN | 1 | no |
| `02_fr_normal.docx` | DOCX, French | FR | 1 | no |
| `03_scanned_ocr_needed.pdf` | scanned PDF, no text layer | EN | 1 | **yes** |
| `04_image_cv_photo.jpg` | image CV (phone photo on a desk) | FR | 1 | **yes** |
| `05_ar_arabic.pdf` | Arabic CV, RTL | AR (+ Latin contacts) | 1 | no |
| `06_mixed_fr_en.pdf` | mixed FR/EN | FR+EN | 1 | no |
| `07_tables_layout.docx` | everything inside Word tables, one nested | FR | 1 | no |
| `08_multipage.pdf` | long CV, 3 pages, repeated footer | EN | 3 | no |
| `09_missing_email.pdf` | no email address anywhere | EN | 1 | no |
| `10_weird_formatting.pdf` | hostile formatting | FR | 1 | no |
| `11_duplicate_exact.pdf` | exact duplicate of 01 (same bytes) | EN | 1 | no |
| `12_duplicate_near_docx.docx` | same candidate, other format and wording | EN | 1 | no |

## The traps, briefly

**03 – scanned.** `pdftotext` returns an empty string; your pipeline has to notice and
fall back to OCR. Greyscale, 0.8° skew, JPEG artefacts, dust and a vertical scanner
streak. Tesseract reads it, but merges the phone digits — good normalisation test.

**04 – photo.** Not a PDF at all. The page sits on a dark desk with a shadow, slight
perspective and a warm colour cast, so it wants cropping and deskewing before OCR.

**05 – Arabic.** Text extracts in visual order, RTL. Section headers are Arabic while
the email and phone stay Latin. Language detection should say Arabic.

**07 – tables.** Iterating over `document.paragraphs` in python-docx returns almost
nothing here; the content lives in `document.tables`, and the skills matrix is a table
inside a table cell. The references block contains someone else's email — a common way
parsers pick up the wrong contact.

**08 – multipage.** Experience runs across a page break, and every page repeats
`Leila Bouzid — Curriculum Vitae / Page N`. Publications carry years that look like
employment dates.

**09 – missing email.** The expected value is `null`. Watch for a parser that grabs
`github.com/mgharbi-ops` and turns it into an address.

**10 – weird.** Two columns (naive extraction interleaves them), name letter-spaced
as `S O F I A N E   Z O U A R I`, email written `sofiane . zouari (at) yahoo . fr`,
phone as `21 6 - 92 - 664 - 105`, skill levels drawn as coloured squares with no text,
dot leaders, a diagonal watermark over the body, and a generation-date footer.

**11 / 12 – duplicates.** 11 is byte-identical to 01, so a hash check catches it before
parsing. 12 is the same candidate as a DOCX with reworded bullets, `03/2021` instead of
`March 2021`, and one genuinely new line (acting tech lead since 01/2024) — hashes are
useless, you need identity matching on email/phone/name, and a merge rule that keeps
the new fact.

## Scoring

```python
import json, pathlib
manifest = json.loads(pathlib.Path("manifest.json").read_text())

for entry in manifest["files"]:
    if entry["file"].startswith("11_"):        # exact duplicate, skip or hash-check
        continue
    result = my_parser.parse(entry["file"])    # your parser
    exp = entry["expected"]
    for field in ("full_name", "email", "phone"):
        if field in exp:
            print(entry["file"], field, result.get(field) == exp[field])
```

Suggested minimum bar before shipping: exact match on name/email/phone for 01, 02, 06,
08; `email is None` for 09; correct employer list for 07; any non-empty text for 03 and
04; and 11 flagged as a duplicate of 01.
