# DebatePanel

> KI-gestuetzte Diskussionsplattform — heterogene Personas diskutieren kontroverse Themen in Echtzeit.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Ueberblick

DebatePanel generiert fuer jedes beliebige Thema automatisch ein diverses Panel aus KI-Personas — inklusive Moderator und Faktencheck-Assistent. Die Personas diskutieren kontrovers, der Moderator steuert den Verlauf, und ein Faktencheck-Assistent prueft Behauptungen live im Web.

**Das Ergebnis:** Eine lebendige, ueberraschende Diskussion mit Perspektiven, die man selbst nicht bedacht haette.

### Features

- **Automatische Panel-Generierung** — 3-10 heterogene Personas inkl. Aussenseiterpositionen
- **Echtzeit-Diskussion** — SSE-Streaming, Moderator steuert Beitragsreihenfolge
- **Faktencheck** — Web-basierte Verifikation von Behauptungen (crawl4ai + DuckDuckGo)
- **Interventionen** — Moderator erkennt Stagnation, bringt neue Impulse
- **Konvergenz-Erkennung** — LLM-basiertes Ende wenn keine neuen Argumente mehr kommen
- **Zusammenfassung** — Automatische Synthese aller Positionen am Ende
- **Export** — Diskussion als Text oder Markdown herunterladen
- **Persona-Management** — Vor Start bearbeiten, loeschen oder eigene hinzufuegen
- **Multilingual** — Diskussionssprache folgt der Eingabe (automatische Erkennung)

---

## Tech Stack

| Layer | Technologie |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 |
| **Frontend** | React 18, TypeScript, Vite 5 |
| **LLM** | Multi-Provider: Alibaba DashScope, OpenAI, Anthropic, Groq, Custom — OpenAI-kompatibel |
| **Event Bus** | bubus (typed events, history tracking) |
| **Web Search** | crawl4ai (Google) + DuckDuckGo (Fallback) |
| **Streaming** | Server-Sent Events (SSE) |
| **Tests** | pytest + pytest-asyncio (Backend), Vitest + Testing Library (Frontend) |

---

## Schnellstart

### Voraussetzungen

- Python 3.11+
- Node.js 18+
- API-Key eines LLM-Providers (siehe unten)

### LLM Provider

DebatePanel unterstuetzt beliebige OpenAI-kompatible APIs. Konfiguration ueber `.env`:

```bash
# Provider waehlen: alibaba | openai | anthropic | groq | custom
LLM_PROVIDER=alibaba

# Alibaba DashScope (Default)
DASHSCOPE_API_KEY=sk-...

# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Groq
GROQ_API_KEY=gsk_...

# Custom OpenAI-kompatibler Provider
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://your-provider.example.com/v1
LLM_MODEL=your-model-name
```

### Installation

```bash
# Repository klonen
git clone https://github.com/<your-username>/debate-panel.git
cd debate-panel

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Trage deinen API-Key in .env ein (siehe LLM Provider oben)

# Frontend
cd ../frontend
npm install
```

### Entwicklung

```bash
# Beides gleichzeitig starten (Backend :8000, Frontend :5173)
./start.sh

# Oder einzeln:
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```

### Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test -- --run
```

---

## Architektur

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
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI App (Lifespan, CORS, Router)
│   │   ├── config.py                   # LOG_LEVEL
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── discussion.py       # Alle Discussion-Endpoints + SSE
│   │   │   │   └── export.py           # TEXT/MARKDOWN Export
│   │   │   └── dependencies.py         # DI, Session Store, Rate Limiting
│   │   ├── agents/
│   │   │   ├── base.py                 # BaseAgent (abstract)
│   │   │   ├── persona.py              # PersonaAgent
│   │   │   ├── moderator.py            # ModeratorAgent (Orchestrator)
│   │   │   ├── fact_checker.py         # FactCheckerAgent
│   │   │   ├── moderator_interventions.py  # InterventionHandler
│   │   │   ├── moderator_synthesis.py      # SynthesisGenerator
│   │   │   └── moderator_factcheck.py      # FactCheckIntegrator
│   │   ├── orchestration/
│   │   │   ├── session.py              # DiscussionSession (Runtime)
│   │   │   ├── event_bus.py            # EventBus (bubus)
│   │   │   └── cleanup.py              # SessionCleanup
│   │   ├── llm/
│   │   │   ├── client.py               # LLMClient (AsyncOpenAI Wrapper)
│   │   │   └── prompts.py              # Alle Prompt-Templates
│   │   ├── models/
│   │   │   ├── agent.py                # AgentType, Agent
│   │   │   ├── discussion.py           # DiscussionState, DiscussionConfig, DiscussionSession
│   │   │   └── message.py              # MessageType, Message
│   │   ├── services/
│   │   │   ├── panel_generator.py      # PanelGenerator
│   │   │   ├── session_storage.py      # SessionWriter (Disk-Persistenz)
│   │   │   ├── session_logger.py       # SessionLogger (JSONL Debug-Logs)
│   │   │   └── session_reload.py       # reload_sessions() beim Startup
│   │   └── utils/
│   │       ├── logger.py               # Strukturierter JSON Logger
│   │       ├── token_counter.py        # tiktoken (8000 Token Default)
│   │       ├── language.py             # langdetect
│   │       └── emoji_map.py            # Emoji-Inferenz
│   ├── tests/                          # 18 Test-Dateien
│   ├── sessions/                       # Disk-Output (gitignored)
│   ├── logs/                           # JSONL Logs (gitignored)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx                     # Haupt-Controller (State Machine, 9 States)
│   │   ├── main.tsx                    # Entry Point + ErrorBoundary
│   │   ├── components/
│   │   │   ├── TopicInput.tsx          # Topic-Eingabe + Model-Auswahl
│   │   │   ├── PersonaReview.tsx       # Panel-Review + CRUD
│   │   │   └── DiscussionView.tsx      # Live-Diskussionsansicht
│   │   ├── services/
│   │   │   └── api.ts                  # API Client
│   │   ├── hooks/
│   │   │   └── useSSE.ts               # SSE Hook (mit Reconnect)
│   │   └── types/
│   │       └── index.ts                # TypeScript Types
│   ├── tests/                          # 8 Test-Dateien
│   └── package.json
└── start.sh                            # Dev-Startup
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
