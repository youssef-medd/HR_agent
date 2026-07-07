# Golden set (spec §5.4)

**Target**: 30 anonymized real CVs (PDF/DOCX/scans, FR/EN/AR mix) + 5 JDs + recruiter reference rankings.

**Deadline**: Week 2 EOD.

## Anonymization protocol
Run `anonymize.py` before committing anything under `cvs/`. Rules:
- Replace `full_name` with `[CANDIDATE_<id>]`
- Replace emails/phones with `[EMAIL_<id>]` / `[PHONE_<id>]`
- Replace postal codes with `[POSTAL_<id>]`
- Replace university names with tier label (e.g. `[TOP100_ENG_FR]`)
- Strip exact DOB → year only
- Delete "Hobbies" / "Associations" sections entirely
- Photos never included in text; ensure image extraction path deletes them
- See `DECISIONS.md` D-004 for rationale (arXiv:2603.05189, arXiv:2407.20371)

## Rankings
`rankings.xlsx` — 5 sheets, one per JD. Columns: `cv_id | recruiter_rank_1_to_30 | notes`. Recruiter fills offline; we compute Spearman vs A4 scores.

## Do NOT commit raw CVs
`.gitignore` excludes `*.pdf|*.docx|*.doc` under this folder. Store originals in shared Drive; only anonymized text extracts + rankings live here.
