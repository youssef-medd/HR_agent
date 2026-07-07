# Golden evaluation set

The golden set is the reference corpus used to evaluate the CV parser (A3), the scoring pipeline (A4), and the bias probe (§5.4 of the technical specification).

## Target composition

- 30 anonymised real CVs — mix of PDF, DOCX, and scanned documents, and of French, English, and Arabic language content.
- 5 real job descriptions.
- Recruiter reference rankings — one ranking per job description, produced independently of the platform.

## Anonymisation protocol

Every CV added to `cvs/` must first pass through `anonymize.py`. The script applies the following transformations:

- `full_name` replaced by `[CANDIDATE_<id>]`
- Email addresses and phone numbers replaced by `[EMAIL_<id>]` / `[PHONE_<id>]`
- Postal codes replaced by `[POSTAL_<id>]`
- Educational institution proper names replaced by a tier label (e.g. `[top-100 engineering school FR]`)
- Precise dates of birth reduced to year granularity
- Sections titled *Hobbies*, *Associations*, or *Extracurriculars* removed
- Photographs excluded from the text extraction pipeline

See `DECISIONS.md` ADR-004 for the rationale behind the extended mask set.

## Recruiter rankings

`rankings.xlsx` contains one worksheet per job description with the columns `cv_id`, `recruiter_rank_1_to_30`, and `notes`. Recruiters fill this file offline; the scoring evaluation computes Spearman rank correlation between the reference ranking and the platform output.

## Repository policy

Raw CV files (`*.pdf`, `*.docx`, `*.doc`) are not committed to this repository. Originals live in the shared secure storage; only the anonymised text extracts and the rankings spreadsheet are versioned here.
