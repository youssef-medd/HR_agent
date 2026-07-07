# Engineering Decision Log

Append-only record of stack decisions, deviations from the technical specification, and any non-obvious engineering call. Each entry follows a lightweight ADR format.

- **Format**: `ADR-NNN · <title>` with **Status**, **Context**, **Decision**, **Consequences**, and **References**.
- **Immutability**: entries are never edited in place. When a decision is superseded, add a new ADR that references and closes the previous one.

---

## ADR-001 · Judge model selection on the Groq inference tier

**Date**: 2026-07-07
**Status**: Accepted

### Context
The specification (§3, Appendix E) lists `llama-3.3-70b-versatile` and `openai/gpt-oss-120b` as approved reasoning/scoring models on the Groq inference tier. On 2026-06-17, Groq announced the deprecation of `llama-3.3-70b-versatile` with a migration path pointing to `openai/gpt-oss-120b` and `qwen/qwen3.6-27b`.

### Decision
Set `MODEL_JUDGE=openai/gpt-oss-120b` as the default reasoning/scoring model. This is one of the two options explicitly permitted by the specification, so this is not a deviation.

### Consequences
- The scoring subsystem (A4) will be evaluated on `openai/gpt-oss-120b` first.
- A comparative evaluation on `qwen/qwen3.6-27b` will run before the final scoring benchmark; the model with the higher Spearman correlation against the recruiter ranking will be retained.

### References
- https://console.groq.com/docs/deprecations
- Technical specification §3, Appendix E

---

## ADR-002 · Langfuse deployment mode

**Date**: 2026-07-07
**Status**: Accepted

### Context
Specification §3 mandates self-hosted Langfuse as the LLM observability layer.

### Decision
Run the full Langfuse self-host stack in `docker-compose.yml`: `langfuse-web`, `langfuse-worker`, `clickhouse`, `minio`. PostgreSQL and Redis are shared with the application (Langfuse uses a dedicated `langfuse` database on the same PostgreSQL server, provisioned by `scripts/init-langfuse-db.sql`).

### Consequences
- Bootstrapping requires four additional container images and approximately two minutes of first-boot migration time.
- Traces, spans, prompts, tokens, and cost never leave the developer's machine or the deployment target.
- No dependency on a third-party observability vendor.

### References
- Technical specification §3
- https://langfuse.com/self-hosting/docker-compose

---

## ADR-003 · Docker Compose service topology

**Date**: 2026-07-07
**Status**: Accepted

### Context
The application services (`api`, `worker`) are being scaffolded before their runtime code exists.

### Decision
Compose runs both `api` and `worker` on `python:3.12-slim` with `command: ["sleep", "infinity"]` as an initial placeholder. Runtime commands are switched to `uvicorn` and `celery` respectively once the corresponding modules are implemented.

### Consequences
- `docker compose up` returns healthy from the outset, enabling infrastructure verification independent of application code.
- The full 8-service topology is exercised end-to-end from the start of the project.

---

## ADR-004 · Extended masking rules for scoring pipeline

**Date**: 2026-07-07
**Status**: Proposed

### Context
Specification §6-A4 requires the scoring judge to be blind to `name`, `photo`, `age`, `gender`, `address`, `nationality`, and `marital status`. Recent empirical evidence indicates that nominally anonymised résumés continue to leak protected attributes through sociocultural markers (institution names, postal codes, hobby sections, precise dates).

### Decision
Propose extending the mask set applied before invocation of the judge model to also cover:
- Educational institution proper names (replaced by a tier label — e.g. `[top-100 engineering school FR]`).
- Precise dates of birth and graduation (retained only at year granularity).
- "Hobbies", "Associations", and "Extracurricular" sections in full.
- Postal codes.
- Candidate photo bytes are never persisted in JSONB.

### Consequences
- Requires a small extension to the masking function used by A4.
- Increases confidence that identity-swap and cohort-swap invariance tests pass.

### References
- Wilson, K. & Caliskan, A. — *Gender, Race, and Intersectional Bias in Resume Screening via Language Model Retrieval*, arXiv:2407.20371 (2024).
- *Small Changes, Big Impact: Demographic Bias in LLM-Based Hiring Through Subtle Sociocultural Markers in Anonymised Resumes*, arXiv:2603.05189.

---

## ADR-005 · Positional-order bias probe

**Date**: 2026-07-07
**Status**: Proposed

### Context
Specification §5.4 defines the bias probe as an identity-swap test (name/gender permutation). Recent evaluations show that judge models exhibit residual positional bias even after full identity masking, and that this bias amplifies when two candidates are compared in a single prompt.

### Decision
Propose two additions to the specified bias probe:
- Feed the same ten masked profiles to the judge in reversed order and assert that the rank correlation between runs is ≥ 0.95.
- Enforce single-candidate scoring: the judge model never receives two candidates in a single prompt.

### Consequences
- Adds one CI-checked invariance property.
- Slightly reduces batching opportunities in the scoring pipeline.

### References
- *Gender and Positional Biases in LLM-Based Hiring Decisions*, arXiv:2505.17049.

---

## ADR-006 · Document parsing stack

**Date**: 2026-07-07
**Status**: Accepted

### Context
Specification §3 lists Docling, PyMuPDF, python-docx, and Tesseract (fra + eng + ara) as approved document-parsing components.

### Decision
Adopt the specified stack without reordering. Parser selection and fallback order will be determined empirically against the golden set once collected, rather than set upfront.

### Consequences
- No premature commitment to a single parser.
- Per-document-class accuracy will be published in the eval report before Demo 1.

---

## ADR-007 · Embedding model

**Date**: 2026-07-07
**Status**: Accepted

### Context
Specification §3 mandates `BAAI/bge-m3` via `sentence-transformers` with a 1024-dimensional dense representation. `bge-m3` also natively supports sparse (lexical) and multi-vector (ColBERT-style) retrieval.

### Decision
Ship the dense-only configuration first, matching the specification. Sparse and multi-vector modes are treated as later optimisation candidates, gated by scoring evaluation results.

---

## ADR-008 · Reference implementations — scope of reuse

**Date**: 2026-07-07
**Status**: Accepted

### Context
Several open-source projects address adjacent problems (`vaibhavarora102/HRRecruitingAgent`, `Sajjad-Amjad/Resume-Parser`, `ksm26/Multi-AI-Agent-Systems-with-crewAI`).

### Decision
These projects are consulted for structural and prompt design ideas only. No source code is copied into this repository. Any code lift requires a prior license review and an explicit ADR.

### Consequences
- Zero license contamination risk.
- Independent codebase with a single authoritative specification.

---

## ADR-009 · Agent orchestration framework

**Date**: 2026-07-07
**Status**: Accepted

### Context
Specification §3 mandates LangChain + LangGraph.

### Decision
Use LangChain + LangGraph exclusively. Rationale: compliance, audit, and human-in-the-loop requirements (§7) benefit from LangGraph's explicit state model, resumable PostgreSQL checkpointer, and native `interrupt()` primitive.

---

## ADR-010 · Golden-set contingency plan

**Date**: 2026-07-07
**Status**: Accepted

### Context
The evaluation harness (§5.4) depends on a golden set of 30 anonymised real CVs, 5 real job descriptions, and recruiter reference rankings. Delivery of these assets depends on external stakeholders.

### Decision
If the internal golden set is not available in time to unblock the scoring evaluation, a public bridge dataset (Kaggle "Resume Dataset") will be used. Bridged rows are flagged in `rankings.xlsx` and replaced by real assets as they arrive.

### Consequences
- Downstream deliverables are never blocked by golden-set availability.
- Publicly-sourced rows are clearly marked and removed before any client-facing evaluation.

---

## ADR-011 · Credential rotation policy for the build phase

**Date**: 2026-07-07
**Status**: Accepted

### Context
Development-phase API credentials (Groq, Gemini, Mistral, Langfuse) and locally-generated secrets are not rotated between iterations.

### Decision
All third-party API keys, `JWT_SECRET`, `PII_MASK_SALT`, and Langfuse infrastructure secrets are rotated before any deployment or demonstration to an external audience.

### Consequences
- Adds a rotation checklist to the hardening phase.
- No development-phase secret ever reaches a production environment.

---

## ADR-012 · MinIO bucket bootstrap

**Date**: 2026-07-07
**Status**: Accepted

### Context
Langfuse v3 persists trace event batches in an S3-compatible object store (MinIO in the self-host stack). The `langfuse` bucket is not created automatically by the MinIO server on first boot, causing every trace upload to fail with `NoSuchBucket` until the bucket is provisioned manually.

### Decision
Add a short-lived `minio-init` service to `docker-compose.yml`. It runs the `minio/mc` client, points it at the internal MinIO endpoint, and creates the `langfuse` bucket with `mc mb --ignore-existing`. The `--ignore-existing` flag makes the step idempotent, so it is safe to run on every `docker compose up`.

### Consequences
- Fresh clones bootstrap into a fully working observability pipeline with a single `docker compose up`.
- No manual step in the MinIO console is required.
- The bootstrap adds a small dependency on the `minio/mc` image but no runtime overhead beyond the first boot.

---

## Template

```
## ADR-NNN · <title>

**Date**: YYYY-MM-DD
**Status**: Proposed | Accepted | Superseded by ADR-MMM

### Context

### Decision

### Consequences

### References
```
