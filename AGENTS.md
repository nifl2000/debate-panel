# AGENTS.md — DebatePanel

## Project Overview

AI-powered debate panel: users enter a topic → LLM generates diverse personas → agents debate in real-time → synthesis.

**Two-stack architecture:**
- **Production:** Cloudflare Workers (TypeScript/Hono) + D1 (SQLite) + KV + Cloudflare AI
- **Development:** Python/FastAPI backend (port 8000) + React/Vite frontend (port 5173)

The Python backend is used for rapid prototyping and feature development. The Workers stack is the production deployment target.

## Quick Start

### Production (Cloudflare Workers)

```bash
# Workers
cd workers
npm ci
wrangler dev                    # Local Workers dev server

# Frontend (pointing to Workers)
cd frontend
VITE_API_BASE_URL=http://localhost:8787 npm run dev
```

### Development (Python Backend)

```bash
# Dev: starts both backend + frontend, skips if already running
./start.sh

# Backend only
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend only
cd frontend && npm run dev

# Required env: backend/.env with DASHSCOPE_API_KEY (see .env.example)
```

## Architecture (Verified from Source)

### Two-Phase Discussion Flow

1. **POST `/api/discussion/start`** → creates `DiscussionSession`, spawns async panel generation, returns immediately with `status: "generating"`
2. **Frontend polls `GET /{id}/status`** every 500ms until `status: "ready"`
3. **POST `/{id}/start-discussion`** → creates `ModeratorAgent` + `FactCheckerAgent`, starts moderator loop
4. **SSE stream** at `GET /{id}/stream` — poll-based (Python) or TransformStream (Workers)

### Key Boundary: Two `DiscussionSession` Classes

- **`app.orchestration.session.DiscussionSession`** — runtime class (state, event bus, conversation log)
- **`app.models.discussion.DiscussionSession`** — Pydantic model (serialization only)
- Runtime class imports Pydantic model via `TYPE_CHECKING` to avoid circular imports

### Session Store

- **Production:** D1 (SQLite) + KV for session state
- **Development:** In-memory dict in `app/api/dependencies.py`: `_session_store: Dict[str, DiscussionSession]`
- **No persistence across restarts** (dev). Sessions written to `backend/sessions/` on disk but never reloaded.
- `SessionCleanup` class exists in `orchestration/cleanup.py` but is **never started** in `main.py`.

### Agent Hierarchy

```
BaseAgent (abstract)
├── PersonaAgent — generates discussion responses
├── ModeratorAgent — orchestrates everything (1152 lines Python)
└── FactCheckerAgent — claim detection + web verification
```

### LLM Providers

| Stack | Provider | Model |
|-------|----------|-------|
| **Production** | Cloudflare AI Workers | `@cf/qwen/qwen2.5-72b-instruct` |
| **Development** | Alibaba DashScope | `qwen3-coder-next` (default) |
| **Development** | Multi-Provider | OpenAI, Anthropic, Groq (configurable) |

## Commands

### Backend (Python)

```bash
cd backend

# Run all tests
pytest                        # 372 tests

# Run single test
pytest tests/test_moderator_agent.py -v

# Run with coverage
pytest --cov=app

# Lint/typecheck: none configured
```

### Workers (TypeScript)

```bash
cd workers

# Dev server
wrangler dev

# Deploy
wrangler deploy

# Type check
npm run typecheck

# Tests
npm test                      # 12 tests

# D1 migrations
npm run db:migrate
```

### Frontend

```bash
cd frontend

# Dev server
npm run dev

# Build
npm run build    # runs tsc && vite build

# Tests
npm test         # vitest (51 tests)
npm test -- --run  # single run (CI mode)
```

### Test Quirks

- **Backend:** `pytest-asyncio` — tests use `@pytest.mark.asyncio`. Heavy `MagicMock`/`AsyncMock` usage.
- **Workers:** Vitest + `@cloudflare/vitest-pool-workers`. Runs in isolated D1/KV environment.
- **Frontend:** Vitest + jsdom. Test files in `frontend/tests/` (not `src/`). Setup file: `tests/setup.ts`.
- **No conftest.py** — fixtures defined inline in test files.
- **No lint/typecheck config** — no ruff, mypy, or eslint configured.

## Known Issues (Verified in Source)

1. **`langdetect` missing from `pyproject.toml`** — imported in `moderator.py` and `persona.py` but not listed as dependency. Works only if installed manually.
2. **Duplicate `language_map`** — same dict (`lang_code → language name`) duplicated 6+ times across `moderator.py`, `persona.py`, `panel_generator.py`.
3. **Duplicate `_infer_emoji()`** — identical function in both `PersonaAgent` and `PanelGenerator`.
4. **`useSSE.ts` hook unused** — `App.tsx` implements its own inline SSE logic. The hook has better features (reconnect, chunking) but is not consumed.
5. **`DiscussionStage.tsx` + `ExportPanel.tsx` unused** — tested components not imported by `App.tsx`.
6. **No graceful shutdown** — `main.py` has no lifespan handler. Running moderator tasks are not cancelled on server stop.
7. **`stopDiscussion()` in `api.ts` returns `{ state: string }` but backend returns `{ synthesis: string }`** — type mismatch; synthesis is lost.
8. **Web search not in Workers** — Fact-checker has no web search in production (LLM-only verification).

## Module Boundaries

| Directory | Owner | Notes |
|-----------|-------|-------|
| `backend/app/api/routes/` | REST endpoints | `discussion.py` (main), `export.py` |
| `backend/app/agents/` | Agent implementations | `moderator.py` is the orchestrator |
| `backend/app/orchestration/` | Session lifecycle | `session.py` (runtime), `event_bus.py` (bubus) |
| `backend/app/llm/` | LLM client + prompts | `client.py` (AsyncOpenAI wrapper), `prompts.py` (templates) |
| `backend/app/services/` | Business logic | `panel_generator.py`, `session_storage.py`, `session_logger.py` |
| `backend/app/models/` | Pydantic data models | `discussion.py`, `agent.py`, `message.py` |
| `backend/sessions/` | Disk output | Written by `SessionWriter`, gitignored |
| `backend/logs/` | JSONL logs | Written by `SessionLogger`, gitignored |
| `workers/src/` | Cloudflare Workers | Hono API, D1/KV, Cloudflare AI |
| `frontend/src/App.tsx` | Primary UI | State machine (9 states), inline styles |
| `frontend/src/services/api.ts` | API client | All REST calls |
| `frontend/src/hooks/useSSE.ts` | SSE hook | **Not used by App.tsx** |
| `frontend/src/components/` | Secondary components | **Not used by App.tsx** |

## Conventions

- **Language**: UI is German, prompts enforce output language matching input topic (auto-detected via `langdetect`).
- **No auth** (V1) — sessions are ephemeral, no user accounts.
- **Moderator is always female** — German "Moderatorin", randomly picked from female names list.
- **Token windowing**: 8000 token default limit, reverse iteration to fit context.
- **SSE format**: `data: {json}\n\n` with heartbeat every iteration.
- **CI/CD**: Push to `master` triggers full test suite + deploy to Cloudflare.

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):

1. **Tests** (parallel):
   - Backend: 372 Python tests
   - Workers: typecheck + 12 TypeScript tests
   - Frontend: 51 TypeScript tests + build

2. **Deploy** (on `master`, after all tests pass):
   - Workers: `wrangler d1 migrations apply --remote` + `wrangler deploy`
   - Frontend: `wrangler pages deploy frontend/dist --project-name=debate-panel`

**Required GitHub Secrets:** `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `WORKER_URL` (optional)
