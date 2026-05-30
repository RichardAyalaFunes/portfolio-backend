# Portfolio Backend

AI-powered FastAPI backend for Richard's portfolio. Implements **Clean Architecture + DDD + Hexagonal** patterns.

Exposes two features:
- **LiveAvatar session management** - generates short-lived tokens for the animated avatar on the frontend
- **OpenAI TTS endpoint** - converts text to PCM audio the avatar plays back in real time

---

## Quick Start

**Requirements:** Python >= 3.14, [Poetry](https://python-poetry.org/)

```bash
# Install dependencies
poetry install

# Copy and fill in secrets
cp .env.example .env   # edit OPENAI_API_KEY, LIVEAVATAR_API_KEY, etc.

# Run dev server (auto-reload)
poetry run fastapi dev src/backend/infrastructure/main.py --host 0.0.0.0 --port 8000 --reload
```

API docs available at: http://localhost:8000/docs

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (TTS + future RAG) |
| `LIVEAVATAR_API_KEY` | LiveAvatar master API key |
| `LIVEAVATAR_BASE_URL` | LiveAvatar API base URL |
| `LIVEAVATAR_AVATAR_ID` | Default avatar ID |
| `OPENAI_TTS_MODEL` | TTS model (default: `tts-1`) |
| `OPENAI_TTS_VOICE` | TTS voice (default: `alloy`) |
| `FRONTEND_ORIGIN` | CORS-allowed origin (e.g. `http://localhost:5173`) |

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/avatar/token` | Create a LiveAvatar session token |
| `POST` | `/api/avatar/start` | Start a session (returns LiveKit credentials) |
| `POST` | `/api/avatar/stop` | Stop a session |
| `POST` | `/api/avatar/keep-alive` | Prevent idle timeout |
| `POST` | `/api/avatar/speak` | Synthesize text to PCM audio (base64) |
| `WS` | `/ws/avatar` | WebSocket bridge - relay `agent.speak` frames to LiveAvatar |
| `GET` | `/health` | Health check |

---

## Project Structure

```
src/backend/
├── domain/          # Business logic - no external dependencies
│   ├── avatar/      # AvatarSession aggregate, value objects
│   └── shared/      # Base classes, domain errors
├── application/     # Use cases - orchestrates domain + ports
│   └── avatar/
│       ├── generate_token/   # GenerateTokenHandler
│       ├── speak/            # SpeakHandler
│       └── ports/            # Driven port interfaces
└── infrastructure/  # Adapters - wires everything together
    ├── adapters/
    │   ├── driver/           # Inbound: REST controllers, WebSocket handler
    │   └── driven/           # Outbound: LiveAvatar client, OpenAI TTS client
    └── config/               # Settings (pydantic-settings), DI, dependencies
```

> Full architecture details: [`docs/portfolio-backend-architecture.md`](docs/portfolio-backend-architecture.md)

---

## Testing

```bash
poetry run pytest
```

Tests live in `tests/`. Currently empty - ready to be filled.

---

## Notes

- LiveAvatar sandbox mode does not support all avatar IDs. If you get a 400 with `"This avatar is not supported in sandbox mode"`, leave `LIVEAVATAR_AVATAR_ID` unset to use the sandbox default.
- On Windows, curl requires double-quoted JSON: `curl ... -d "{}"`