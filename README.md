# DebatePanel

> KI-gestuetzte Diskussionsplattform — heterogene Personas diskutieren kontroverse Themen in Echtzeit.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Cloudflare Workers](https://img.shields.io/badge/Cloudflare%20Workers-F38020.svg)](https://workers.cloudflare.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Ueberblick

DebatePanel generiert fuer jedes beliebige Thema automatisch ein diverses Panel aus KI-Personas — inklusive Moderator und Faktencheck-Assistent. Die Personas diskutieren kontrovers, der Moderator steuert den Verlauf, und ein Faktencheck-Assistent prueft Behauptungen.

**Das Ergebnis:** Eine lebendige, ueberraschende Diskussion mit Perspektiven, die man selbst nicht bedacht haette.

### Features

- **Automatische Panel-Generierung** — 3-7 heterogene Personas inkl. Aussenseiterpositionen
- **Echtzeit-Diskussion** — SSE-Streaming, Moderator steuert Beitragsreihenfolge
- **Faktencheck** — LLM-basierte Verifikation von Behauptungen
- **Interventionen** — Moderator erkennt Stagnation, bringt neue Impulse
- **Konvergenz-Erkennung** — LLM-basiertes Ende wenn keine neuen Argumente mehr kommen
- **Zusammenfassung** — Automatische Synthese aller Positionen am Ende
- **Export** — Diskussion als Text oder Markdown herunterladen
- **Persona-Management** — Vor Start bearbeiten, loeschen oder eigene hinzufuegen
- **Multilingual** — Diskussionssprache folgt der Eingabe (automatische Erkennung)

---

## Tech Stack

### Production (Cloudflare)

| Layer | Technologie |
|-------|-------------|
| **Backend** | Cloudflare Workers + Hono (TypeScript) |
| **Frontend** | React 18, TypeScript, Vite 5, Cloudflare Pages |
| **Datenbank** | Cloudflare D1 (SQLite) + Drizzle ORM |
| **Session Storage** | Cloudflare KV |
| **LLM** | Cloudflare AI Bindings (`@cf/qwen/qwen2.5-72b-instruct`) |
| **CI/CD** | GitHub Actions → `git push master` → auto-deploy |

### Legacy Backend (Python/FastAPI — development only)

| Layer | Technologie |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 |
| **LLM** | Multi-Provider: Alibaba DashScope, OpenAI, Anthropic, Groq |
| **Event Bus** | bubus (typed events, history tracking) |
| **Web Search** | crawl4ai (Google) + DuckDuckGo (Fallback) |

> **Hinweis:** Das Python-Backend dient ausschliesslich der lokalen Entwicklung und Feature-Prototypisierung. Fuer die Produktion wird der TypeScript/Cloudflare-Stack deployed.

---

## Schnellstart

### Produktion: Cloudflare Deployment

```bash
# 1. D1 Datenbank erstellen
cd workers
wrangler d1 create debate-panel-db
# Aktualisiere database_id in wrangler.jsonc mit der returned ID

# 2. KV Namespace erstellen
wrangler kv:namespace create SESSION_KV
# Aktualisiere id und preview_id in wrangler.jsonc mit den returned IDs

# 3. D1 Migration anwenden
wrangler d1 migrations apply debate-panel-db --local

# 4. Workers deployen
wrangler deploy

# 5. Frontend deployen
cd ../frontend
VITE_API_BASE_URL=https://<dein-worker>.workers.dev npm run build
wrangler pages deploy dist --project-name=debate-panel
```

Oder via CI/CD: Push nach `master` deployed automatisch (siehe `.github/workflows/ci.yml`).

### Lokal: Development mit Python Backend

#### Voraussetzungen

- Python 3.11+
- Node.js 18+
- API-Key eines LLM-Providers (siehe unten)

#### LLM Provider

DebatePanel unterstuetzt beliebige OpenAI-kompatible APIs. Konfiguration ueber `.env`:

```bash
# Provider waehlen: alibaba | openai | anthropic | groq | custom
LLM_PROVIDER=alibaba

# Alibaba DashScope (Default)
DASHSCOPE_API_KEY=sk-...
```

#### Installation

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Frontend
cd ../frontend
npm install
```

#### Entwicklung

```bash
# Beides gleichzeitig starten (Backend :8000, Frontend :5173)
./start.sh

# Oder einzeln:
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```

#### Lokal: Workers Development

```bash
cd workers
wrangler dev
# In anderem Terminal:
cd frontend && VITE_API_BASE_URL=http://localhost:8787 npm run dev
```

### Tests

```bash
# Workers (Production)
cd workers && npm test        # 12 tests

# Frontend
cd frontend && npm test -- --run  # 51 tests

# Legacy Backend (Python)
cd backend && pytest          # 372 tests
```

---

## Architektur

### Production Stack (Cloudflare Workers)

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
                       ─────────┘
```

### Legacy Backend (Python/FastAPI)

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Session                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Event Bus (bubus)                        │   │
│  │                                                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Persona  │  │ Persona  │  │  Fact-Checker    │   │   │
│  │  │ Agent 1  │  │ Agent 2  │  │    (async)       │   │   │
│  │  └────┬─────┘  └────┬─────┘  └──────┬───────────┘   │   │
│  │       │             │                │              │   │
│  │       └─────────────┴────────────────┘              │   │
│  │                     │                               │   │
│  │              ┌──────▼──────┐                        │   │
│  │              │  Moderator  │                        │   │
│  │              │(Orchestrator)                        │   │
│  │              └──────┬──────┘                        │   │
│  └─────────────────────┼───────────────────────────────┘   │
│                        │                                   │
│                   ┌────▼────┐                              │
│                   │  SSE    │ (poll-based, 500ms)          │
│                   │ Stream  │                              │
│                   └────┬────┘                              │
└────────────────────────┼────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │  React  │
                    │ Client  │
                    └─────────┘
```

### Datenfluss

1. **Topic eingeben** → `POST /api/discussion/start` → Session erstellt, Panel-Generierung im Hintergrund
2. **Status pollen** → `GET /{id}/status` alle 500ms → Personas erscheinen
3. **Diskussion starten** → `POST /{id}/start-discussion` → Moderator-Loop beginnt
4. **SSE Stream** → `GET /{id}/stream` → Echtzeit-Updates im Frontend
5. **Diskussion stoppen** → `POST /{id}/stop` → Synthese wird generiert

### Projektstruktur

```
debate-panel/
├── backend/                          # Legacy Python/FastAPI (Development)
│   ├── app/
│   │   ├── main.py                   # FastAPI App (Lifespan, CORS, Router)
│   │   ├── config.py                 # LOG_LEVEL
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── discussion.py     # Alle Discussion-Endpoints + SSE
│   │   │   │   └── export.py         # TEXT/MARKDOWN Export
│   │   │   └── dependencies.py       # DI, Session Store, Rate Limiting
│   │   ├── agents/
│   │   │   ├── base.py               # BaseAgent (abstract)
│   │   │   ├── persona.py            # PersonaAgent
│   │   │   ├── moderator.py          # ModeratorAgent (Orchestrator)
│   │   │   ├── fact_checker.py       # FactCheckerAgent
│   │   │   ├── moderator_interventions.py  # InterventionHandler
│   │   │   ├── moderator_synthesis.py      # SynthesisGenerator
│   │   │   └── moderator_factcheck.py      # FactCheckIntegrator
│   │   ├── orchestration/
│   │   │   ├── session.py            # DiscussionSession (Runtime)
│   │   │   ├── event_bus.py          # EventBus (bubus)
│   │   │   └── cleanup.py            # SessionCleanup
│   │   ├── llm/
│   │   │   ├── client.py             # LLMClient (AsyncOpenAI Wrapper)
│   │   │   └── prompts.py            # Alle Prompt-Templates
│   │   ├── models/
│   │   │   ├── agent.py              # AgentType, Agent
│   │   │   ├── discussion.py         # DiscussionState, DiscussionConfig
│   │   │   └── message.py            # MessageType, Message
│   │   ├── services/
│   │   │   ├── panel_generator.py    # PanelGenerator
│   │   │   ├── session_storage.py    # SessionWriter (Disk-Persistenz)
│   │   │   ├── session_logger.py     # SessionLogger (JSONL Debug-Logs)
│   │   │   └── session_reload.py     # reload_sessions() beim Startup
│   │   └── utils/
│   │       ├── logger.py             # Strukturierter JSON Logger
│   │       ├── token_counter.py      # tiktoken (8000 Token Default)
│   │       ├── language.py           # langdetect
│   │       └── emoji_map.py          # Emoji-Inferenz
│   ├── tests/                        # 372 tests
│   ├── sessions/                     # Disk-Output (gitignored)
│   ├── logs/                         # JSONL Logs (gitignored)
│   ── pyproject.toml
├── frontend/                         # React + TypeScript (Production)
│   ├── src/
│   │   ├── App.tsx                   # Haupt-Controller (State Machine, 9 States)
│   │   ├── main.tsx                  # Entry Point + ErrorBoundary
│   │   ├── components/
│   │   │   ├── TopicInput.tsx        # Topic-Eingabe + Model-Auswahl
│   │   │   ├── PersonaReview.tsx     # Panel-Review + CRUD
│   │   │   └── DiscussionView.tsx    # Live-Diskussionsansicht
│   │   ├── services/
│   │   │   └── api.ts                # API Client
│   │   ├── hooks/
│   │   │   └── useSSE.ts             # SSE Hook (mit Reconnect)
│   │   └── types/
│   │       └── index.ts              # TypeScript Types
│   ├── tests/                        # 51 tests
│   ├── wrangler.toml                 # Cloudflare Pages Config
│   └── package.json
├── workers/                          # Cloudflare Workers (Production)
│   ├── src/
│   │   ├── index.ts                  # Hono API (alle Endpoints + SSE)
│   │   ├── agents/                   # BaseAgent, Persona, Moderator, FactChecker
│   │   ├── db/                       # Drizzle Schema + D1 Migrationen
│   │   ├── services/                 # PanelGenerator, SessionStore, Language
│   │   ├── llm.ts                    # Cloudflare AI Binding
│   │   ├── prompts.ts                # Prompt-Templates
│   │   └── types.ts                  # TypeScript Types
│   ├── tests/                        # 12 tests
│   ├── wrangler.jsonc                # Workers Config
│   ├── drizzle.config.ts             # Drizzle ORM Config
│   └── package.json
├── .github/workflows/ci.yml          # GitHub Actions (Test + Deploy)
├── start.sh                          # Dev-Startup (Python Backend)
├── ARCHITECTURE.md                   # Detaillierte System-Architektur
├── PRD_DebatePanel_v1.md             # Product Requirements Document
└── AGENTS.md                         # Session Instructions fuer KI-Agenten
```

---

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `POST` | `/api/discussion/start` | Session erstellen, Panel-Generierung starten |
| `GET` | `/api/discussion/{id}/status` | Generierungsstatus pollen |
| `PUT` | `/api/discussion/{id}/personas/{pid}` | Persona bearbeiten |
| `DELETE` | `/api/discussion/{id}/personas/{pid}` | Persona loeschen |
| `POST` | `/api/discussion/{id}/personas` | Neue Persona hinzufuegen |
| `POST` | `/api/discussion/{id}/start-discussion` | Diskussion starten (Moderator-Loop) |
| `POST` | `/api/discussion/{id}/inject` | Moderator-Instruktion injizieren |
| `GET` | `/api/discussion/{id}` | Volle Discussion abrufen |
| `POST` | `/api/discussion/{id}/pause` | Diskussion pausieren |
| `POST` | `/api/discussion/{id}/resume` | Diskussion fortsetzen |
| `POST` | `/api/discussion/{id}/stop` | Diskussion stoppen + Synthese |
| `GET` | `/api/discussion/{id}/stream` | SSE Stream (Echtzeit) |
| `GET` | `/api/discussion/{id}/export` | Export (TEXT/MARKDOWN) |
| `GET` | `/health` | Health Check |

---

## Roadmap

| Version | Status | Features |
|---------|--------|----------|
| **V1 — Watch Mode** | ✅ Aktuell | Topic eingeben, zuschauen, Synthese, Export |
| **V2 — Edit Mode** | Geplant | Panel vor Start konfigurieren, Personas bearbeiten/hinzufuegen/loeschen |
| **V3 — Play Mode** | Geplant | Nutzer tritt als eigene Persona in die Diskussion ein |

---

## Lizenz

MIT — siehe [LICENSE](LICENSE) fuer Details.
