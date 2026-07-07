# DECISIONS.md — Welyne HR AI Agent

Append-only log. Every stack deviation from the spec, every non-obvious call, every "why did we do that" gets an entry. Format: date, decision, reason, ref.

---

## 2026-07-07 — Phase 0 kickoff decisions

### D-001 · MODEL_JUDGE = openai/gpt-oss-120b (in-spec alternative)
- **Decision**: Set `MODEL_JUDGE=openai/gpt-oss-120b`.
- **Reason**: Spec §3 explicitly lists **both** `llama-3.3-70b-versatile` **and** `openai/gpt-oss-120b` as valid reasoning/scoring models. `llama-3.3-70b-versatile` was deprecated by Groq on 2026-06-17 (external event, not our choice) so `openai/gpt-oss-120b` is the working spec-approved option.
- **Not a spec deviation** — spec allows both, we picked the one that still runs.
- **Ref**: https://console.groq.com/docs/deprecations · Spec §3 stack table.
- **Re-eval**: Week 4 with scoring eval.

### D-002 · Langfuse SELF-HOSTED (spec-strict)
- **Decision**: Run Langfuse in `docker-compose.yml` per spec §3 "Langfuse auto-hébergé (OSS)". Adds 4 services: `langfuse-web`, `langfuse-worker`, `clickhouse`, `minio`. Shares `postgres` and `redis` with app.
- **Reason**: Spec says self-host. User confirmed "stick with frameworks and tools they obliged me to do".
- **Boot**: `docker compose up -d` → open `http://localhost:3000` → create Langfuse admin → create project "welyne-hr" → copy Public + Secret keys → paste in `.env` → restart api container.
- **Ref**: Spec §3 · https://langfuse.com/self-hosting/docker-compose

### D-003 · Docker Compose = full spec stack
- **Decision**: `docker-compose.yml` runs `postgres` (pgvector), `redis`, `api`, `worker`, `langfuse-web`, `langfuse-worker`, `clickhouse`, `minio`. Day 1 `api`/`worker` are placeholder `sleep infinity`; real code Day 2/3.
- **Reason**: Full spec stack from Day 1 = fewer surprises later. Placeholder trick keeps boot green before app code exists.
- **Ref**: Spec §2 architecture diagram.

### D-004 · Bias mask extension — PROPOSAL to manager, not applied yet
- **Status**: NOT applied in code. Awaiting manager green-light.
- **Proposal**: Extend spec §6-A4 mask list (`name/photo/age/gender/address/nationality/marital`) to also strip: **university proper names → tier label**, **exact dates → year-ranges only**, **hobbies/associations sections**, **postal codes**, **candidate photo bytes never in JSONB**.
- **Reason for proposal**: arXiv:2603.05189 · arXiv:2407.20371 — nominally anonymized resumes leak protected signals via sociocultural markers.
- **Action**: raise at first manager sync. If approved → new decision entry + code lands before Demo 1.

### D-005 · Bias probe positional-swap — PROPOSAL, not applied
- **Status**: NOT applied. Awaiting manager green-light.
- **Proposal**: Extend spec §5.4 bias probe (name/gender swap) with positional-swap test: same 10 masked CVs in reversed order → rank correlation ≥ 0.95.
- **Reason**: arXiv:2505.17049 shows positional bias survives name masking.
- **Also proposes**: A4 scores each CV alone, never batch-compares two in one prompt.
- **Action**: raise with mask extension proposal.

### D-006 · Parser stack = spec-strict, no ordering deviation
- **Decision**: Use `Docling`, `PyMuPDF`, `python-docx`, `Tesseract fra+eng+ara` — exactly as spec §3 lists. No opinion on primary/fallback until we benchmark on real golden set.
- **Reason**: Spec lists all four without ordering. Ordering decision deferred to Week 2 empirical results.
- **Ref**: Spec §3.

### D-007 · BGE-M3 default mode
- **Decision**: Use BGE-M3 dense embeddings via `sentence-transformers` per spec §3. Sparse/multi-vector modes = **later exploration only**, not Week 2 scope.
- **Reason**: Spec says "BAAI/bge-m3 via sentence-transformers · 1024 dim". Dense-only matches spec.
- **Ref**: Spec §3 embeddings row.

### D-008 · Reference repos = read-only study
- **Decision**: Read `vaibhavarora102/HRRecruitingAgent`, `Sajjad-Amjad/Resume-Parser`, `ksm26/Multi-AI-Agent-Systems-with-crewAI` L7 for pattern ideas only. **No code lifted.**
- **Reason**: Spec toolchain (LangGraph + FastAPI + Pydantic) is authoritative. Repos help sanity-check our design without contaminating license or drifting from spec.

### D-009 · Agent framework = LangGraph (spec)
- **Decision**: LangChain + LangGraph per spec §3. No CrewAI, no alternative.
- **Ref**: Spec §3.

### D-010 · Golden set fallback
- **Decision**: If Welyne cannot supply 30 real CVs by end of Week 1, bridge with public dataset (Kaggle "Resume Dataset") — mark bridged rows in `rankings.xlsx`, swap out later.
- **Reason**: A3/A4 evaluation blocked without a golden set. Bridge avoids Week 2 slippage.
- **Owner**: Confirm with manager (Q3).

### D-011 · Dev API keys — rotate before ship
- **Decision**: Dev-phase Groq / Gemini / Mistral / Langfuse keys treated as ephemeral. Not rotating during build.
- **Debt**: Before any prod deploy or demo to external audience, rotate ALL provider keys + regenerate `JWT_SECRET` + `PII_MASK_SALT`.
- **Reason**: User confirmed dev-only phase, rotation deferred to pre-ship hardening.
- **Owner**: Add to Week 4 hardening checklist.

---

## Template for future entries

### D-NNN · <short title>
- **Decision**:
- **Reason**:
- **Ref**:
- **Re-eval / owner**:
