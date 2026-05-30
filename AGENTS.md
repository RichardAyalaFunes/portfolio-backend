# AGENTS.md - Portfolio Backend

## What Is This Project

This is the backend for **Richard Xavier Ayala Funes's** personal portfolio website. It is a **production-grade FastAPI service** that exists for two purposes:

1. **Technical showcase** - demonstrates Clean Architecture + DDD + Hexagonal patterns in a real deployed system.
2. **Portfolio features** - powers a real-time AI avatar and (planned) an RAG chatbot on the portfolio website.

The project is intentionally over-engineered for a portfolio backend. The complexity is the point - it is a living demonstration of enterprise backend patterns.

---

## Architecture in One Sentence

Three concentric layers (Domain -> Application -> Infrastructure), where **nothing in an inner layer imports from an outer layer**, ever.

```
Domain        pure Python dataclasses, no I/O, no frameworks
   ^
Application   use cases (command/handler/port pattern), no FastAPI, no HTTP
   ^
Infrastructure  FastAPI controllers, httpx clients, pydantic-settings, DI wiring
```

---

## Current Features (Implemented)

### Avatar System
The only feature live today. The frontend shows an animated LiveAvatar that speaks to the visitor.

**Handshake flow:**
```
Frontend
  -> POST /api/avatar/token       # backend creates a session with LiveAvatar API
  -> POST /api/avatar/start       # backend starts the session, returns LiveKit credentials
  -> WebSocket /ws/avatar         # frontend sends text, backend synthesizes TTS and relays PCM frames
  -> POST /api/avatar/stop        # when visitor leaves
```

**TTS flow:** Frontend sends text to `POST /api/avatar/speak`. Backend calls OpenAI TTS with `response_format=pcm` (24 kHz / 16-bit / mono) and returns base64-encoded audio. The frontend chunks this into <=1s frames and pushes them through the WebSocket.

### Planned: RAG Chatbot
Visitors will be able to ask natural language questions about Richard's background. The system will use OpenAI embeddings + pgvector (Supabase) for semantic search over CV and project data, then GPT-4o-mini to generate grounded answers. **Not yet implemented.**

---

## File and Folder Map

```
backend/
├── README.md                        # Quick-start for humans
├── AGENTS.md                        # This file
├── pyproject.toml                   # Poetry + project metadata
├── .env                             # Secrets (never committed)
│
├── docs/
│   ├── portfolio-backend-prd.md     # Product requirements (why, what, users)
│   ├── portfolio-backend-architecture.md  # Technical deep-dive (how)
│   └── portfolio-backend-roadmap.md # Phased delivery plan
│
├── src/backend/
│   ├── domain/
│   │   ├── avatar/
│   │   │   ├── entities/            # AvatarSession (aggregate root)
│   │   │   ├── value_objects.py     # SessionToken, AvatarState, AvatarSessionId
│   │   │   └── repository.py       # IAvatarSessionRepository (driven port interface)
│   │   └── shared/                  # Base classes: AggregateRoot, ValueObject, DomainError
│   │
│   ├── application/
│   │   └── avatar/
│   │       ├── generate_token/      # Command + Port + Handler for token creation
│   │       ├── speak/               # Command + Port + Handler for TTS synthesis
│   │       └── ports/               # IAvatarAPIClient interface (driven port)
│   │
│   └── infrastructure/
│       ├── main.py                  # FastAPI app bootstrap, lifespan, CORS, router wiring
│       ├── config/
│       │   ├── settings.py          # Pydantic-settings (reads .env)
│       │   └── dependencies.py      # FastAPI Depends() factories - the DI container
│       └── adapters/
│           ├── driver/              # Inbound adapters (they call the application)
│           │   ├── rest/
│           │   │   └── avatar_controller.py   # POST /api/avatar/* routes
│           │   └── websocket/
│           │       └── avatar_ws_handler.py   # WS /ws/avatar bridge
│           └── driven/              # Outbound adapters (application calls these)
│               ├── liveavatar/
│               │   └── avatar_client.py       # httpx wrapper around LiveAvatar API
│               └── openai/
│                   └── openai_tts_client.py   # AsyncOpenAI TTS call
│
└── tests/                           # pytest - currently skeleton, ready to populate
```

---

## Key Patterns to Know

### Command / Handler / Port
Every use case follows this triple:
- `command.py` - frozen dataclass, the input DTO
- `port.py` - abstract base class defining the use case interface (driver port)
- `handler.py` - concrete implementation; depends only on driven port interfaces

### Dependency Injection
No DI framework. FastAPI `Depends()` factories live in `config/dependencies.py`. They read from `app.state` (populated during lifespan) and build handler objects. Controllers receive dependencies via `Annotated[..., Depends(...)]` type aliases.

### Settings
`pydantic-settings` reads from `.env`. One singleton via `functools.lru_cache` (`get_settings()`). All secrets are accessed through this object - never `os.environ` directly.

---

## External Services

| Service | Purpose | Key |
|---|---|---|
| LiveAvatar | Animated avatar sessions | `LIVEAVATAR_API_KEY` |
| OpenAI | TTS audio synthesis | `OPENAI_API_KEY` |
| Supabase (planned) | pgvector for RAG | `SUPABASE_URL` / `SUPABASE_KEY` |

---

## Dependency Rules (Enforced by Architecture)

- `domain/` imports: only Python stdlib
- `application/` imports: `domain/` + stdlib only
- `infrastructure/` imports: anything (FastAPI, httpx, openai SDK, etc.)

Violations of this rule are bugs, not style issues. If you are adding code, check which layer it belongs to before importing.

---

## What to Work On Next

From `docs/portfolio-backend-roadmap.md`:
1. RAG chatbot domain model (`domain/chatbot/`)
2. Supabase conversation repository
3. OpenAI embeddings service + seed CLI
4. `POST /api/chat/messages` endpoint
5. Unit + integration test suite
