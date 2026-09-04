"""A3 duplicate handling — file hash, identity match, and profile merge.

Driven by the reference corpus in `evals/golden/cvs` (see its manifest):
`11_duplicate_exact.pdf` is byte-identical to `01_en_normal.pdf`, and
`12_duplicate_near_docx.docx` is the same candidate in another format with one
genuinely new fact.
"""

from __future__ import annotations

from orchestrator.dedup import _union_fuzzy, file_sha256, merge_profiles


def test_file_hash_is_stable_and_content_addressed():
    assert file_sha256(b"abc") == file_sha256(b"abc")
    assert file_sha256(b"abc") != file_sha256(b"abd")


def test_merge_keeps_the_newer_document_facts():
    """Newest wins: the whole point of re-applying with an updated CV."""
    merged = merge_profiles(
        {"full_name": "Omar Ben Salah", "summary": "old summary"},
        {"full_name": "OMAR BEN SALAH", "summary": "acting tech lead since 01/2024"},
    )
    assert merged["summary"] == "acting tech lead since 01/2024"
    assert merged["full_name"] == "OMAR BEN SALAH"


def test_merge_fills_gaps_from_the_older_profile():
    """An empty field in the newer parse means 'not mentioned', not 'deleted'."""
    merged = merge_profiles(
        {"email": "omar@x.io", "location": "Tunis", "years_experience": 8.0},
        {"email": "", "location": "", "years_experience": None},
    )
    assert merged["email"] == "omar@x.io"
    assert merged["location"] == "Tunis"
    assert merged["years_experience"] == 8.0


def test_merge_keeps_history_the_newer_cv_dropped():
    """A shorter re-application must not erase an employer."""
    merged = merge_profiles(
        {"experiences": [
            {"company": "Paymee", "title": "Senior Backend Engineer"},
            {"company": "Vermeg", "title": "Junior Software Developer"},
        ]},
        {"experiences": [{"company": "Paymee", "title": "Senior Backend Engineer"}]},
    )
    companies = [e["company"] for e in merged["experiences"]]
    assert companies == ["Paymee", "Vermeg"]


def test_merge_collapses_a_certification_written_two_ways():
    merged = merge_profiles(
        {"certifications": ["Certified Kubernetes Application Developer, CKAD (2021)"]},
        {"certifications": ["CKAD (2021)"]},
    )
    assert merged["certifications"] == ["CKAD (2021)"]


def test_similar_but_distinct_skills_are_not_collapsed():
    """Java is a substring of JavaScript — they must stay separate skills."""
    out = _union_fuzzy(["JavaScript"], ["Java"])
    assert sorted(out) == ["Java", "JavaScript"]


def test_union_prefers_the_newer_spelling_and_dedupes_case():
    assert _union_fuzzy(["python"], ["Python", "Go"]) == ["python", "Go"]
