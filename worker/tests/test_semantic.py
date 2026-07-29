"""A4 stage 2 — semantic pre-ranking features (offline hashing embedder)."""

from __future__ import annotations

from orchestrator.semantic import EMBED_DIM, cosine, embed, semantic_enabled, semantic_features


def test_embed_returns_unit_vectors():
    [v] = embed(["Python SQL backend"])
    assert len(v) == EMBED_DIM
    assert abs(sum(x * x for x in v) - 1.0) < 1e-6  # L2-normalized


def test_cosine_identical_and_disjoint():
    a = embed(["python postgresql docker"])[0]
    same = embed(["python postgresql docker"])[0]
    other = embed(["cooking gardening painting"])[0]
    assert cosine(a, same) > 0.99
    assert cosine(a, other) < 0.2  # disjoint tokens -> near-orthogonal


def test_semantic_features_reward_overlap():
    spec = {"must_have": ["Python", "PostgreSQL"], "missions": ["build backend APIs"]}
    strong = {
        "skills": ["Python", "PostgreSQL", "Docker"],
        "summary": "Backend engineer",
        "experiences": [{"title": "Backend Dev", "summary": "built APIs"}],
    }
    weak = {
        "skills": ["Photoshop", "Illustrator"],
        "summary": "Graphic designer",
        "experiences": [{"title": "Designer", "summary": "made posters"}],
    }
    f_strong = semantic_features(spec, strong)
    f_weak = semantic_features(spec, weak)
    assert f_strong["skills_sim"] > f_weak["skills_sim"]
    assert 0.0 <= f_strong["prerank_score"] <= 1.0
    assert f_strong["prerank_score"] > f_weak["prerank_score"]


def test_semantic_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEMANTIC_ENABLED", raising=False)
    assert semantic_enabled() is False


def test_score_node_adds_semantic_when_enabled(db_factory, monkeypatch):
    from orchestrator import nodes
    from orchestrator.agents.scorer import ScoreResult

    monkeypatch.setenv("SEMANTIC_ENABLED", "1")
    monkeypatch.setattr(
        nodes, "score_candidate",
        lambda *a, **k: ScoreResult(overall=70, recommendation="shortlist"),
    )
    from app.models.application import Application
    from app.models.job import Job

    with db_factory() as db:
        db.add(Job(id=1, title="Backend", status="published",
                   spec={"spec": {"must_have": ["Python"], "missions": ["APIs"]}}))
        row = Application(job_id=1, candidate_ref="a@b.c", state="PARSED",
                          payload={"cv": {"skills": ["Python"], "experiences": []}, "jd_text": "x"})
        db.add(row)
        db.commit()
        db.refresh(row)
        app_id = row.id

    with db_factory() as db:
        nodes.score_node(db, {"application_id": app_id, "stage": "PARSED", "attempt": 1})

    with db_factory() as db:
        score = db.get(Application, app_id).payload["score"]
        assert "semantic" in score
        assert "prerank_score" in score["semantic"]
