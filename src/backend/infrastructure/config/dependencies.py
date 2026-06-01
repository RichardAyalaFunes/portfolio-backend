"""
Dependency injection — composition root.

Long-lived clients (httpx.AsyncClient, AsyncOpenAI, LiveAvatarClient,
OpenAITTSClient) are constructed once by the FastAPI lifespan in
`main.py` and stashed on `app.state`. The provider functions below
read them from the request's app state. Per-request handler classes
(GenerateTokenHandler, SpeakHandler) are cheap and built per call.
"""

from typing import Annotated

from fastapi import Depends, Request

from backend.application.avatar.generate_token.handler import GenerateTokenHandler
from backend.application.avatar.generate_token.port import IGenerateTokenUseCase
from backend.application.avatar.speak.handler import SpeakHandler
from backend.application.avatar.speak.port import ISpeakUseCase
from backend.application.realtime.create_session.handler import CreateRealtimeSessionHandler
from backend.application.realtime.create_session.port import ICreateRealtimeSessionUseCase
from backend.infrastructure.adapters.driven.liveavatar.avatar_client import LiveAvatarClient
from backend.infrastructure.adapters.driven.openai.openai_realtime_client import OpenAIRealtimeClient
from backend.infrastructure.adapters.driven.openai.openai_tts_client import OpenAITTSClient
from backend.infrastructure.config.settings import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_liveavatar_client(request: Request) -> LiveAvatarClient:
    """Provide the lifespan-shared LiveAvatarClient driven adapter."""
    return request.app.state.liveavatar_client  # type: ignore[no-any-return]


def get_openai_tts_client(request: Request) -> OpenAITTSClient:
    """Provide the lifespan-shared OpenAI TTS driven adapter."""
    return request.app.state.openai_tts_client  # type: ignore[no-any-return]


LiveAvatarClientDep = Annotated[LiveAvatarClient, Depends(get_liveavatar_client)]
OpenAITTSClientDep = Annotated[OpenAITTSClient, Depends(get_openai_tts_client)]


def get_generate_token_use_case(
    client: LiveAvatarClientDep,
    settings: SettingsDep,
) -> IGenerateTokenUseCase:
    """Wire GenerateTokenHandler with its dependencies."""
    return GenerateTokenHandler(
        avatar_api_client=client,
        default_avatar_id=settings.liveavatar_avatar_id,
        default_voice_id=settings.liveavatar_voice_id,
        default_context_id=settings.liveavatar_context_id,
        default_language=settings.liveavatar_language,
        default_mode=settings.liveavatar_mode,
        default_is_sandbox=settings.liveavatar_sandbox,
    )


def get_speak_use_case(tts: OpenAITTSClientDep) -> ISpeakUseCase:
    """Wire SpeakHandler with the OpenAI TTS adapter."""
    return SpeakHandler(tts_client=tts)


# ── Realtime ─────────────────────────────────────────────────────────────────


def get_openai_realtime_client(request: Request) -> OpenAIRealtimeClient:
    """Provide the lifespan-shared OpenAI Realtime driven adapter."""
    return request.app.state.openai_realtime_client  # type: ignore[no-any-return]


OpenAIRealtimeClientDep = Annotated[OpenAIRealtimeClient, Depends(get_openai_realtime_client)]


def get_create_realtime_session_use_case(
    client: OpenAIRealtimeClientDep,
    settings: SettingsDep,
) -> ICreateRealtimeSessionUseCase:
    """Wire CreateRealtimeSessionHandler with its dependencies."""
    return CreateRealtimeSessionHandler(
        realtime_client=client,
        default_model=settings.openai_realtime_model,
        default_voice=settings.openai_realtime_voice,
    )
