# Welyne HR AI Agent

Multi-agent recruitment platform. From job posting to onboarding.

Spec: `/docs/spec-v1.0.md` (not in repo yet — add on Day 5).
Plan: see `~/.claude/plans/memoized-spinning-island.md` (per-week breakdown).
Decisions: `DECISIONS.md`.

---

## Stack (default per spec §3)
- **API**: FastAPI + Uvicorn (Python 3.12)
- **Worker**: Celery + LangGraph (Python 3.12)
- **DB**: PostgreSQL 16 + pgvector
- **Cache/Queue**: Redis 7
- **LLM**: Groq (primary) → Gemini → Mistral (fallback chain); models per `.env`
- **Observability**: Langfuse cloud (Week 1) → self-host (Week 4)
- **Frontend**: Next.js 15 + Tailwind + shadcn/ui
- **Auth**: JWT + bcrypt (admin / recruiter / viewer)

---

## Quick start (Week 1 — Phase 0 demo gate)

### 1. Prerequisites
- Docker Desktop running (`docker --version` → 24+)
- Node 20+ (Day 4 frontend)
- Python 3.12+ (Day 2 gateway)

### 2. Get LLM provider keys
- **Groq**: https://console.groq.com → API Keys → create
- **Gemini** (fallback): https://aistudio.google.com/apikey
- **Mistral** (fallback, FR): https://console.mistral.ai

Langfuse runs self-hosted in Compose — keys generated after boot (step 5).

### 3. Fill `.env`
```powershell
cp .env.example .env
notepad .env
```
Paste `GROQ_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`.

Generate 4 secrets locally (do NOT paste in chat):
```powershell
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('LANGFUSE_NEXTAUTH_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('LANGFUSE_SALT=' + secrets.token_hex(32))"
python -c "import secrets; print('LANGFUSE_ENCRYPTION_KEY=' + secrets.token_hex(32))"
```
Paste each into `.env`. Also set `POSTGRES_PASSWORD`, `REDIS_AUTH`, `CLICKHOUSE_PASSWORD`, `MINIO_ROOT_PASSWORD`, `LANGFUSE_INIT_USER_PASSWORD` to non-default strings.

### 4. Boot
```powershell
docker compose up -d
docker ps
```
Expect 8 healthy containers: `postgres`, `redis`, `api`, `worker`, `clickhouse`, `minio`, `langfuse-worker`, `langfuse-web`.

First boot takes ~2–3 min (Langfuse runs DB migrations on first start).

### 5. Verify pgvector
```powershell
docker exec -it welyne-postgres psql -U welyne -d welyne_hr -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
```

### 6. Get Langfuse API keys (self-hosted)
Open http://localhost:3000 → sign in with `LANGFUSE_INIT_USER_EMAIL` + `LANGFUSE_INIT_USER_PASSWORD` from `.env` → project "welyne-hr" auto-created → Settings → API Keys → Create → copy `pk-lf-...` and `sk-lf-...` → paste into `.env` as `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`:
```powershell
docker compose restart api worker
```

### 7. Day 2 onwards
- Day 2 — `api/scripts/hello_gateway.py` triggers 1 Groq call → visible in Langfuse UI → **Phase 0 demo gate cleared**.
- Day 3 — Alembic migrations + auth.
- Day 4 — GitHub Actions CI + frontend login page.
- Day 5 — Golden set + Demo 0 dry-run.

---

## Repo layout
```
HR_agent/
├── api/                  # FastAPI service (gateway, auth, endpoints)
│   ├── app/              # main.py, gateway.py, models/, routes/
│   └── scripts/          # hello_gateway.py, seed_admin.py, ...
├── worker/               # Celery + LangGraph agents A0..A9
├── frontend/             # Next.js dashboard + candidate portal
├── prompts/              # /<agent>/<name>@vN.md, mirrored to prompt_versions
│   ├── a3/               # extract prompts
│   └── a4/               # judge/rubric prompts
├── evals/                # eval harness (§5.4)
│   ├── golden/           # anonymized CVs + JDs + recruiter rankings
│   └── reports/          # eval outputs per prompt_version
├── migrations/           # Alembic
├── docker-compose.yml
├── .env.example
├── .gitignore
├── DECISIONS.md          # append-only log of every stack decision
└── README.md
```

---

## Ways of working (spec §8.2 — non-negotiable)
- Trunk-based, small PRs, review by another intern within 24 h.
- CI green before merge.
- Friday demo on real data every week.
- Every bug report links a Langfuse trace.
- `DECISIONS.md` entry for every stack deviation.
- Definition of done: code + test + migration + trace + doc line here.

---

## Security & compliance
- Candidate data = personal data (Tunisian law 2004-63 / GDPR).
- Scoring never sees name/photo/age/gender/address/university/postal-code/hobbies.
- No rejection or offer sent without recruiter click (LangGraph `interrupt()`).
- 12-month retention default. `POST /candidates/{id}/erase` = GDPR delete.
- See `DECISIONS.md` D-004, D-005 for extended mask rules.
