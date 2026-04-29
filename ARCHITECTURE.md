# DebatePanel - System Architecture Document

**Version:** 1.2  
**Date:** April 2026  
**Status:** Verified against source code (Implementation-accurate)

---

## Executive Summary

DebatePanel V1 (MVP - Watch Mode) implements a **session-based event bus architecture** with a stateful Moderator orchestrator. The system supports two backends:

- **Production:** Cloudflare Workers (TypeScript/Hono) + D1 (SQLite) + KV — deployed via GitHub Actions
- **Development:** Python/FastAPI with bubus event bus, crawl4ai web search — local-only

**Core Principle**: Backend owns all state. Frontend reflects state via SSE streaming. Agents are stateless — they receive context, return responses. Moderator orchestrates flow, detects stalls, integrates fact-checks.

---

## 1. Tech Stack Decisions

### Frontend (Production)

- **React 18 (Vite 5)** - Pure SPA, TypeScript
- **No SSR** - Client-side rendering sufficient for V1
- **Testing:** Vitest + React Testing Library + jsdom (51 tests)
- **No component framework** - All styles inline in `App.tsx`
- **Deploy:** Cloudflare Pages via `wrangler pages deploy`

### Production Backend (Cloudflare Workers)

- **TypeScript + Hono** - Edge runtime, minimal cold start
- **Cloudflare D1** - SQLite database for session state + Drizzle ORM
- **Cloudflare KV** - Session storage for active discussions
- **Cloudflare AI Binding** - `@cf/qwen/qwen2.5-72b-instruct` model
- **Testing:** Vitest + `@cloudflare/vitest-pool-workers` (12 tests)
- **Deploy:** `wrangler deploy` via GitHub Actions on `master` push
- **SSE:** `TransformStream` for native streaming at the edge

### Development Backend (Python/FastAPI — Legacy)

- **Python 3.11+ (FastAPI)** - Async-first, SSE support, LLM integration
- **Pydantic v2** - Data validation and serialization
- **Testing:** pytest + pytest-asyncio (372 tests, 18 test files)
- **No lint/typecheck** - No ruff, mypy, or pylint configured

### LLM Services

| Stack | Provider | Model |
|-------|----------|-------|
| **Production** | Cloudflare AI Workers | `@cf/qwen/qwen2.5-72b-instruct` |
| **Development** | Alibaba DashScope | `qwen3-coder-next` (default) |
| **Development** | Multi-Provider | OpenAI, Anthropic, Groq (configurable) |

- **OpenAI SDK** (`AsyncOpenAI`) - Used in Python backend for compatibility
- **API key:** `DASHSCOPE_API_KEY` (dev) or Cloudflare AI Binding (prod)

### Web Search (Fact-check — Development only)

- **crawl4ai** (primary) - Google search scraping with CSS extraction, 15s timeout
  - Trusted German sources prioritized (wikipedia.de, bpb.de, tagesschau.de)
  - `CacheMode.BYPASS` for fresh results
- **DuckDuckGo** (`ddgs`, fallback) - Used when crawl4ai fails
- **Production:** Web search not yet implemented in Workers (V2)

### Event Bus (Development)

- **bubus library** - Typed events with history tracking (max 100 events via deque)
- Event types: `AgentMessageEvent`, `FactCheckEvent`, `StallDetectedEvent`, `ModeratorCommandEvent`

### Streaming

- **SSE (Server-Sent Events)** - Unidirectional, HTTP-standard
  - **Production:** `TransformStream` at the edge (native streaming)
  - **Development:** Poll-based — checks `conversation_log` every 500ms
  - Sends complete messages (not character-by-character)
  - Heartbeat every iteration to keep connection alive
  - **V3:** WebSocket for bidirectional user input

### Language

- **Multilingual** - Auto-detect input language via `langdetect`
  - Discussion language follows input language
  - UI remains German (V1)

### Authentication

- **No Auth (V1)** - Session-only, no permanent storage
  - **Production:** D1 + KV for session state
  - **Development:** In-memory `_session_store` dict
  - No user accounts required

---

## 2. Core Architecture Pattern

### 2.1 Session-based Event Bus (Development) / D1+KV (Production)

**Development (Python):**
```
─────────────────────────────────────────────────────────────┐
│                        FastAPI Session                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Event Bus (bubus)                        │   │
│  │                                                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Persona  │  │ Persona  │  │  Fact-checker    │   │   │
│  │  │ Agent 1  │  │ Agent 2  │  │    (async)       │   │   │
│  │  └────┬─────┘  └────┬─────┘  └──────┬───────────┘   │   │
│  │       │             │                │              │   │
│  │       └─────────────────────────────┘              │   │
│  │                     │                               │   │
│  │              ┌──────▼──────┐                        │   │
│  │              │  Moderator  │◄── Pattern matching    │   │
│  │              │(Orchestrator)    (agreement words,   │   │
│  │              └──────┬──────┘     speaker count)     │   │
│  └─────────────────────┼───────────────────────────────┘   │
│                        │                                   │
│                   ┌────▼────┐                              │
│                   │ SSE     │ (poll-based, 500ms)          │
│                   │ Stream  │                              │
│                   └────┬────┘                              │
└────────────────────────┼────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ React   │
                    │ Client  │
                    └─────────┘
```

**Production (Cloudflare Workers):**
```
┌─────────────────────────────────────────────────────────────┐
│                   Cloudflare Workers (Hono)                  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  PersonaAgent │  │  PersonaAgent │  │  FactChecker     │   │
│  │              │  │              │  │  (async)         │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘   │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                           │                                 │
│                    ┌──────▼──────┐                          │
│                    │ ModeratorAgent│                         │
│                    │ (Orchestrator)│                         │
│                    └──────┬──────┘                          │
│                           │                                 │
│                    ┌──────▼──────┐                          │
│                    │ D1 (SQLite) │  Session State           │
│                    │ KV (Session)│  KV Storage              │
│                    └──────┬──────┘                          │
│                           │                                 │
│                    ┌──────▼──────┐                          │
│                    │ SSE Stream  │  (TransformStream)       │
│                    └──────┬──────┘                          │
└───────────────────────────┼──────────────────────────────────┘
                            │
                       ┌────▼────┐
                       │  React  │
                       │ Client  │
                       └─────────┘
```

### 2.2 Key Components

#### DiscussionSession — Two Classes (Important!)

**Runtime class** (`app/orchestration/session.py` — Python):
```python
class DiscussionSession:
    id: str                      # UUID
    topic: str                   # User-provided topic
    state: DiscussionState       # PAUSED, ACTIVE, COMPLETED, ERROR
    phase: str                   # "INTRODUCTION" → "DISCUSSION" → "COMPLETED"
    event_bus: EventBus          # bubus instance
    agents: dict[str, BaseAgent] # All agents
    conversation_log: list[Message]
    config: DiscussionConfig
    _lock: asyncio.Lock          # Thread-safe message addition
    _inject_queue: asyncio.Queue # User instruction injection
    _session_writer: SessionWriter
```

**Pydantic model** (`app/models/discussion.py`) — serialization only. Runtime class imports it via `TYPE_CHECKING` to avoid circular imports.

**Workers equivalent** (`workers/src/db/schema.ts`):
```typescript
// D1 schema: sessions, personas, messages tables
// KV: active session state for real-time access
```

#### ModeratorAgent (Orchestrator — 1152 lines Python)

The `moderator_loop()` runs the entire discussion:

```python
async def moderator_loop(self):
    # 1. Introduction round: each persona.introduce()
    # 2. Phase → DISCUSSION
    # 3. Main loop:
    #    - Moderator speaks every 3 persona messages
    #    - Select next speaker (scoring: name mentions +0.5, speak count -0.2, recent exclusion)
    #    - Generate persona response with token-windowed context
    #    - Check intervention need (≤2 unique speakers in last 6 messages)
    #    - Check convergence every 5 iterations near max_messages
    #    - Process pending instruction injections
    #    - 0.5s sleep between iterations
    # 4. Generate final synthesis
```

**Intervention types** (`_choose_intervention_type()`):
- `CLARIFYING` — default
- `PROVOCATIVE` — when agreement words detected ("zustimmung", "genau", "agree", etc.)
- `SUMMARIZING` — every 8 messages
- `REDIRECTING` — when ≤2 unique speakers in last 10 messages

**Protocols for testability:** `StallDetectorProtocol`, `FactCheckerProtocol`

#### Agent Hierarchy

```
BaseAgent (abstract)
├── PersonaAgent — generates discussion responses, 60s timeout
── ModeratorAgent — orchestrates everything (1152 lines)
└── FactCheckerAgent — claim detection + web verification
```

---

## 3. Stall Detection & Intervention (Actual Implementation)

The stall detection is **not hybrid multi-signal** as originally planned. The actual implementation uses simple pattern matching:

| Mechanism | Trigger | Response |
|-----------|---------|----------|
| **Speaker count** | ≤2 unique speakers in last 6-10 messages | `_check_intervention_need()` → status message "🎯 Moderator greift ein..." |
| **Agreement words** | "zustimmung", "genau", "richtig", "einig", "agree", "exactly" in recent text | `_choose_intervention_type()` → `PROVOCATIVE` intervention |
| **Message count** | Every 8 messages | `SUMMARIZING` intervention |
| **Convergence** | LLM judges last 10 messages near `max_messages` | `detect_convergence()` → returns "CONVERGED" or "CONTINUE" |

There is **no timeout-based stall detection** and **no multi-signal requirement** in the current implementation. The original hybrid detection design (2+ signals required) was simplified.

---

## 4. Project Structure (Verified from Source)

### 4.1 Monorepo Layout

```
debate_panel/
├── backend/                          # Legacy Python/FastAPI (Development only)
│   ├── app/
│   │   ├── main.py                   # FastAPI app entry (CORS, routers, /health)
│   │   ├── config.py                 # LOG_LEVEL only
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── discussion.py     # All discussion endpoints (639 lines)
│   │   │   │   └── export.py         # TEXT/MARKDOWN export (PDF = 501)
│   │   │   └── dependencies.py       # _session_store, rate limiting, DI
│   │   ├── agents/
│   │   │   ├── base.py               # BaseAgent (abstract)
│   │   │   ├── persona.py            # PersonaAgent (281 lines)
│   │   │   ├── moderator.py          # ModeratorAgent (1152 lines)
│   │   │   ├── fact_checker.py       # FactCheckerAgent (504 lines)
│   │   │   ├── moderator_interventions.py  # InterventionHandler
│   │   │   ├── moderator_synthesis.py      # SynthesisGenerator
│   │   │   ── moderator_factcheck.py      # FactCheckIntegrator
│   │   ├── orchestration/
│   │   │   ├── session.py            # DiscussionSession runtime class (368 lines)
│   │   │   ├── event_bus.py          # bubus event bus
│   │   │   └── cleanup.py            # SessionCleanup (exists, NOT started)
│   │   ├── llm/
│   │   │   ├── client.py             # LLMClient (AsyncOpenAI wrapper)
│   │   │   └── prompts.py            # All prompt templates
│   │   ├── models/
│   │   │   ├── discussion.py         # Pydantic models (DiscussionSession, Config, State)
│   │   │   ├── agent.py              # Agent model, AgentType enum
│   │   │   └── message.py            # Message model, MessageType enum
│   │   ├── services/
│   │   │   ├── panel_generator.py    # PanelGenerator (659 lines)
│   │   │   ├── session_storage.py    # SessionWriter (disk persistence)
│   │   │   ├── session_logger.py     # SessionLogger (JSONL logs)
│   │   │   └── session_reload.py     # reload_sessions() at startup
│   │   └── utils/
│   │       ├── logger.py             # Structured JSON logging
│   │       ├── token_counter.py      # tiktoken counting (8000 token default)
│   │       ├── language.py           # langdetect utilities
│   │       └── emoji_map.py          # Emoji inference
│   ├── tests/                        # 18 test files (372 tests)
│   ├── scripts/                      # Utility scripts (gitignored)
│   ├── sessions/                     # Disk output (gitignored)
│   ├── logs/                         # JSONL logs (gitignored)
│   └── pyproject.toml                # setuptools, no lint config
── frontend/                         # React + TypeScript (Production)
│   ├── src/
│   │   ├── App.tsx                   # PRIMARY UI (state machine, 9 states, inline styles)
│   │   ├── main.tsx                  # Entry point + ErrorBoundary
│   │   ├── components/
│   │   │   ├── TopicInput.tsx        # Topic input + model selector
│   │   │   ├── PersonaReview.tsx     # Panel review + CRUD
│   │   │   ├── DiscussionView.tsx    # Live discussion view
│   │   │   ├── DiscussionStage.tsx   # EXISTS but NOT used by App.tsx
│   │   │   └── ExportPanel.tsx       # EXISTS but NOT used by App.tsx
│   │   ├── hooks/
│   │   │   └── useSSE.ts             # EXISTS (reconnect, chunking) but NOT used
│   │   ├── services/
│   │   │   └── api.ts                # All REST API calls
│   │   └── types/
│   │       └── index.ts              # TypeScript types
│   ├── tests/                        # 4 test files (51 tests)
│   ├── wrangler.toml                 # Cloudflare Pages config
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts              # jsdom, setupFiles: tests/setup.ts
│   └── tsconfig.json
├── workers/                          # Cloudflare Workers (Production)
│   ├── src/
│   │   ├── index.ts                  # Hono API (all endpoints + SSE via TransformStream)
│   │   ├── agents/
│   │   │   ├── base.ts               # BaseAgent (abstract)
│   │   │   ├── persona.ts            # PersonaAgent
│   │   │   ├── moderator.ts          # ModeratorAgent (orchestrator)
│   │   │   └── fact-checker.ts       # FactCheckerAgent
│   │   ├── db/
│   │   │   ├── schema.ts             # Drizzle ORM schema
│   │   │   ├── index.ts              # D1 client
│   │   │   ── migrations/           # SQL migrations
│   │   ├── services/
│   │   │   ├── panel-generator.ts    # PanelGenerator
│   │   │   ├── session-store.ts      # SessionStore (D1 + KV)
│   │   │   ├── language.ts           # Language detection
│   │   │   └── tokens.ts             # Token counting
│   │   ├── llm.ts                    # Cloudflare AI Binding wrapper
│   │   ├── prompts.ts                # All prompt templates
│   │   └── types.ts                  # TypeScript types
│   ├── tests/                        # 4 test files (12 tests)
│   ├── wrangler.jsonc                # Workers config (D1, KV, AI binding)
│   ├── drizzle.config.ts             # Drizzle ORM config
│   ├── tsconfig.json
│   ├── vitest.config.ts              # @cloudflare/vitest-pool-workers
│   └── package.json
├── .github/workflows/ci.yml          # GitHub Actions (Test + Deploy)
├── ARCHITECTURE.md                   # This document
├── PRD_DebatePanel_v1.md             # Product requirements document
├── AGENTS.md                         # Session instructions for AI agents
├── README.md                         # Project overview + quick start
── start.sh                          # Dev startup (Python backend + frontend)
```

### 4.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/discussion/start` | Create session, async panel generation |
| `GET` | `/api/discussion/{id}/status` | Poll panel generation status |
| `PUT` | `/api/discussion/{id}/personas/{pid}` | Update persona |
| `DELETE` | `/api/discussion/{id}/personas/{pid}` | Delete persona |
| `POST` | `/api/discussion/{id}/personas` | Add persona |
| `POST` | `/api/discussion/{id}/start-discussion` | Start discussion (moderator + fact_checker) |
| `POST` | `/api/discussion/{id}/inject` | Inject user instruction |
| `GET` | `/api/discussion/{id}` | Get full discussion state |
| `POST` | `/api/discussion/{id}/pause` | Pause discussion |
| `POST` | `/api/discussion/{id}/resume` | Resume discussion |
| `POST` | `/api/discussion/{id}/stop` | Stop + generate synthesis |
| `GET` | `/api/discussion/{id}/stream` | SSE streaming endpoint |
| `GET` | `/api/discussion/{id}/export` | Export (TEXT/MARKDOWN) |
| `GET` | `/health` | Health check |

---

## 5. Data Flow

```
1. User enters topic → POST /api/discussion/start
   → Creates DiscussionSession, stores in session store
   → Returns session_id immediately (status: "generating")
   → Spawns generate_panel_async() background task

2. Frontend polls GET /{id}/status every 500ms
   → When status="ready": shows PANEL_READY with personas

3. User clicks "Start Discussion" → POST /{id}/start-discussion
   → Creates FactCheckerAgent + ModeratorAgent
   → moderator.start_loop() → asyncio.create_task(moderator_loop) [Python]
   → moderator.start_loop() → ctx.waitUntil(...) [Workers]
   → Frontend connects SSE: EventSource(/{id}/stream)

4. Moderator loop:
   a. Introduction round: each persona.introduce() → LLM → add_message
   b. Phase = DISCUSSION
   c. Loop:
      - Select next speaker (scoring algorithm)
      - Get context (token-windowed, 8000 default)
      - persona.generate_response(context) → LLM
      - session.add_message() → event_bus.publish(AgentMessageEvent) [Python]
      - session.add_message() → KV/D1 update [Workers]
      - Moderator detects claims → fact_checker.check_claim() (async)
      - Fact check result → event_bus.publish(FactCheckEvent) [Python]
      - Fact check result → add_message(FACT_CHECK) [Workers]
      - Moderator integrates fact check → add_message
      - Check convergence → if converged, generate synthesis → stop

5. SSE stream delivers new messages:
   → Production: TransformStream pushes chunks as they arrive
   → Development: Polls conversation_log every 500ms
   → Formats as data: {json}\n\n
   → Frontend parses, deduplicates (Set<message_id>), appends

6. User clicks Stop → POST /{id}/stop
   → session.stop_discussion()
   → moderator.generate_synthesis() → LLM
   → session.finalize_session() → writes to D1/disk
   → Returns synthesis to frontend
```

---

## 6. Key Design Decisions

### Decision 1: Moderator as Orchestrator
**Choice:** Stateful orchestrator (not passive observer)
- Proactively intervenes, integrates fact-checks, detects convergence
- Intervention through prompts (not commands) maintains conversation continuity

### Decision 2: Shared Context for All Agents
**Choice:** All agents see full conversation history (with token windowing)
- Default limit: 8000 tokens, reverse iteration to fit
- Uses tiktoken `cl100k_base` encoding (Python) or equivalent (Workers)

### Decision 3: Backend-Owned State
**Choice:** Backend is single source of truth, frontend reflects
- **Production:** D1 (SQLite) + KV for session state
- **Development:** In-memory `_session_store` dict — no persistence across restarts
- Disk output in `backend/sessions/` (written but never reloaded)

### Decision 4: SSE for Streaming
**Choice:** Server-Sent Events (poll-based in dev, TransformStream in prod)
- **Production:** `TransformStream` at the edge — native streaming
- **Development:** SSE endpoint polls `conversation_log` every 500ms
- Sends complete messages, not character-by-character streaming
- Simpler than WebSocket (sufficient for V1)

### Decision 5: Panel Size 3-10 (not 3-5)
**Choice:** `MIN_PANEL_SIZE = 3`, `MAX_PANEL_SIZE = 10`
- PRD specified 3-5, but implementation allows up to 10
- Validation requires ≥2 unique stances, outsider presence check (relaxed)

### Decision 6: Dual-Stack Architecture
**Choice:** Python/FastAPI for rapid prototyping, TypeScript/Workers for production
- Python: faster iteration, richer ecosystem (crawl4ai, bubus)
- Workers: zero cold start, edge computing, native SSE, lower cost
- Both stacks share the same API contract and prompt templates

---

## 7. Known Issues & Technical Debt

| Issue | Location | Impact | Stack |
|-------|----------|--------|-------|
| `langdetect` missing from `pyproject.toml` | `moderator.py`, `persona.py`, `panel_generator.py` | Works only if manually installed | Python |
| Duplicate `language_map` dict | 6+ copies across `moderator.py`, `persona.py`, `panel_generator.py` | DRY violation | Python |
| Duplicate `_infer_emoji()` | `PersonaAgent` + `PanelGenerator` | Identical function, two locations | Python |
| `useSSE.ts` hook unused | `App.tsx` has inline SSE logic | Better features (reconnect, chunking) not consumed | Frontend |
| `DiscussionStage.tsx` + `ExportPanel.tsx` unused | Tested but not imported by `App.tsx` | Dead code | Frontend |
| No graceful shutdown | `main.py` — no lifespan handler | Running tasks not cancelled on stop | Python |
| `SessionCleanup` not started | `cleanup.py` exists, never instantiated | Sessions accumulate indefinitely | Python |
| `stopDiscussion()` type mismatch | `api.ts` returns `{ state }`, backend returns `{ synthesis }` | Synthesis is lost | Frontend |
| No App.tsx tests | Main UI component has zero coverage | Regression risk | Frontend |
| Web search not in Workers | Fact-checker has no web search in production | Fact-checks are LLM-only in prod | Workers |

---

## 8. Critical Risks & Mitigations

| Risk | Mitigation | Status | Stack |
|------|------------|--------|-------|
| **Context window overflow** | Token counting + sliding window (8000 tokens) | ✅ Implemented | Both |
| **LLM API failures** | Exponential backoff (3 retries) | ✅ Implemented | Both |
| **Fact-checker blocking** | Async execution + 15s timeout | ✅ Implemented | Python |
| **Stall false positives** | Simple pattern matching (no multi-signal) | ⚠️ Simplified from original design | Python |
| **Memory leaks** | `SessionCleanup` class exists | ❌ Not started in `main.py` | Python |
| **SSE connection drops** | Heartbeat every iteration | ⚠️ No auto-reconnect in App.tsx | Frontend |
| **Google scraping fragility** | crawl4ai CSS selectors may break | ⚠️ DuckDuckGo fallback exists | Python |
| **D1 rate limits** | Batched writes, KV for hot paths | ⚠️ Needs monitoring | Workers |

---

## 9. V2/V3 Compatibility

| Component | V1 (Current) | V2/V3 (Planned) |
|-----------|-------------|-----------------|
| **Session State** | D1 + KV (prod) / In-memory (dev) | Redis |
| **Agent Roles** | Persona, Moderator, Fact-checker | Add UserAgent (V3) |
| **Message Types** | AGENT, FACT_CHECK, MODERATOR, SYSTEM | Add UserMessage, EditMessage |
| **Event Bus** | bubus (Python) / Direct (Workers) | Redis Pub/Sub (V3) |
| **Streaming** | SSE (TransformStream / poll-based) | WebSocket (V3) |
| **Persistence** | D1 + KV (prod) / Disk (dev, never reloaded) | Database |
| **Panel config** | V2: Edit personas before start | — |
| **User participation** | — | V3: User joins as persona |
| **Web Search** | crawl4ai + DuckDuckGo (dev only) | Edge-compatible search API |

---

## 10. CI/CD Pipeline

```
push to master
    │
    ├── backend-tests (Python) — 372 tests
    ├── workers-tests (TypeScript) — typecheck + 12 tests
    └── frontend-tests (TypeScript) — 51 tests + build
            │
            ├── deploy-workers → wrangler deploy (D1 migrations + Workers)
            └── deploy-frontend → wrangler pages deploy
```

**Required GitHub Secrets:**
| Secret | Purpose |
|--------|---------|
| `CLOUDFLARE_API_TOKEN` | Deploy Workers + Pages |
| `CLOUDFLARE_ACCOUNT_ID` | Account identification |
| `WORKER_URL` (optional) | Override Worker URL (default: `https://debate-panel-api.nicoflohr.workers.dev`) |

---

*Document updated to reflect verified implementation with Cloudflare Workers production stack (v1.2). Original design document created by Prometheus (Plan Builder).*
