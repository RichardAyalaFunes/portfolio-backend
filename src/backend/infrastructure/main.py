"""FastAPI application bootstrap."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from backend.infrastructure.adapters.driven.liveavatar.avatar_client import LiveAvatarClient
from backend.infrastructure.adapters.driven.openai.openai_realtime_client import OpenAIRealtimeClient
from backend.infrastructure.adapters.driven.openai.openai_tts_client import OpenAITTSClient
from backend.infrastructure.adapters.driver.rest.avatar_controller import router as avatar_router
from backend.infrastructure.adapters.driver.rest.realtime_controller import router as realtime_router
from backend.infrastructure.adapters.driver.websocket.avatar_ws_handler import (
    router as avatar_ws_router,
)
from backend.infrastructure.config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Build long-lived clients once and stash on app.state.

    Sharing httpx.AsyncClient and AsyncOpenAI across requests avoids the
    per-request connection setup overhead and respects the libraries'
    documented usage pattern.
    """
    settings = get_settings()

    http_client = httpx.AsyncClient(timeout=15.0)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    app.state.http_client = http_client
    app.state.openai_client = openai_client
    app.state.liveavatar_client = LiveAvatarClient(
        http_client=http_client,
        api_keys=settings.liveavatar_api_keys,
        base_url=settings.liveavatar_base_url,
    )
    app.state.openai_tts_client = OpenAITTSClient(
        client=openai_client,
        default_model=settings.openai_tts_model,
        default_voice=settings.openai_tts_voice,
    )
    app.state.openai_realtime_client = OpenAIRealtimeClient(
        http_client=http_client,
        api_key=settings.openai_api_key,
    )

    try:
        yield
    finally:
        await http_client.aclose()
        await openai_client.close()


settings = get_settings()
_is_prod = settings.environment == "production"

app = FastAPI(
    title="Portfolio Backend",
    version="0.1.0",
    description=(
        "AI-powered portfolio backend — Clean Architecture + DDD + Hexagonal. "
        "Provides LiveAvatar LITE mode session management and an OpenAI TTS endpoint "
        "that produces 24 kHz / 16-bit / mono PCM audio for the avatar's `agent.speak` WS frames."
    ),
    # Disable interactive docs in production — no need to expose the API surface publicly.
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(avatar_router)
app.include_router(avatar_ws_router)
app.include_router(realtime_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"], summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok"}
