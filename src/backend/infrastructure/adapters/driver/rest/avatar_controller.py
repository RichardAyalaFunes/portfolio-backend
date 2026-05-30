"""
Avatar REST controller — driver adapter (inbound).

Exposes the LiveAvatar LITE session management endpoints plus the
backend-owned `/speak` TTS endpoint to the frontend. The LiveAvatar
master API key and the OpenAI key are never returned in responses.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.application.avatar.generate_token.command import GenerateTokenCommand
from backend.application.avatar.generate_token.port import IGenerateTokenUseCase
from backend.application.avatar.speak.command import SpeakCommand
from backend.application.avatar.speak.port import ISpeakUseCase
from backend.infrastructure.adapters.driven.liveavatar.avatar_client import (
    LiveAvatarClient,
    LiveAvatarHTTPError,
)
from backend.infrastructure.adapters.driven.openai.openai_tts_client import OpenAITTSError
from backend.infrastructure.config.dependencies import (
    get_generate_token_use_case,
    get_liveavatar_client,
    get_speak_use_case,
)

router = APIRouter(prefix="/api/avatar", tags=["avatar"])


# ── Request / Response models ────────────────────────────────────────────────


class CreateTokenRequest(BaseModel):
    avatar_id: Optional[str] = Field(
        default=None,
        description="Override the default avatar ID. Leave null to use the configured default.",
    )
    max_session_duration: int = Field(
        default=120,
        ge=60,
        le=1200,
        description="Session lifetime in seconds (60–1200). LiveAvatar hard-caps at 1200.",
    )


class CreateTokenResponse(BaseModel):
    session_id: str
    session_token: str


class StartSessionRequest(BaseModel):
    session_token: str = Field(
        description="The session_token returned by /api/avatar/token; used as Bearer auth to LiveAvatar.",
    )


class StartSessionResponse(BaseModel):
    session_id: str
    livekit_url: str
    livekit_client_token: str
    ws_url: str
    max_session_duration: int = 0


class StopSessionRequest(BaseModel):
    session_id: str = Field(description="LiveAvatar session ID returned by /token.")
    reason: str = Field(
        default="USER_CLOSED",
        description=(
            "LiveAvatar stop reason. Valid values per docs include USER_CLOSED, "
            "USER_DISCONNECTED, IDLE_TIMEOUT, NO_CREDITS, MAX_DURATION_REACHED, "
            "AGENT_HANG_UP, AVATAR_DELETED, SERVER_ERROR, ZOMBIE_SESSION_REAP, UNKNOWN."
        ),
    )


class KeepAliveRequest(BaseModel):
    session_id: str = Field(description="LiveAvatar session ID returned by /token.")


class SessionActionResponse(BaseModel):
    session_id: str
    status: str


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000, description="Text the avatar should speak.")
    voice: Optional[str] = Field(
        default=None,
        description="Optional OpenAI TTS voice override (alloy, echo, fable, onyx, nova, shimmer).",
    )


class SpeakResponse(BaseModel):
    audio_b64: str = Field(description="Base64-encoded PCM 16-bit / 24 kHz / mono audio.")
    sample_rate: int = Field(default=24000, description="Always 24000 Hz to match LiveAvatar.")
    duration_ms: int


# ── Dependency aliases ────────────────────────────────────────────────────────

GenerateTokenUseCaseDep = Annotated[IGenerateTokenUseCase, Depends(get_generate_token_use_case)]
SpeakUseCaseDep = Annotated[ISpeakUseCase, Depends(get_speak_use_case)]
LiveAvatarClientDep = Annotated[LiveAvatarClient, Depends(get_liveavatar_client)]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/token",
    response_model=CreateTokenResponse,
    summary="Create a LITE-mode session token",
    description=(
        "Step 1 of the LiveAvatar handshake. Calls POST /v1/sessions/token with "
        "the master X-API-KEY and returns the short-lived session_token the frontend "
        "uses to call /api/avatar/start. The master API key is never exposed."
    ),
)
async def create_token(
    request: CreateTokenRequest,
    use_case: GenerateTokenUseCaseDep,
) -> CreateTokenResponse:
    try:
        result = await use_case.execute(
            GenerateTokenCommand(
                avatar_id=request.avatar_id,
                max_session_duration=request.max_session_duration,
            )
        )
        return CreateTokenResponse(
            session_id=result.session_id,
            session_token=result.session_token,
        )
    except LiveAvatarHTTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/start",
    response_model=StartSessionResponse,
    summary="Start an avatar session",
    description=(
        "Step 2 of the LiveAvatar handshake. POST /v1/sessions/start with "
        "Authorization: Bearer <session_token>. Returns the LiveKit room "
        "credentials (for video/audio playback) plus the LITE WebSocket URL "
        "(for `agent.speak` frames)."
    ),
)
async def start_session(
    request: StartSessionRequest,
    client: LiveAvatarClientDep,
) -> StartSessionResponse:
    try:
        result = await client.start_session(request.session_token)
        return StartSessionResponse(
            session_id=result.session_id,
            livekit_url=result.livekit_url,
            livekit_client_token=result.livekit_client_token,
            ws_url=result.ws_url,
            max_session_duration=result.max_session_duration,
        )
    except LiveAvatarHTTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/stop",
    response_model=SessionActionResponse,
    summary="Stop an avatar session",
    description="Releases the session and stops billing. Call when the user leaves.",
)
async def stop_session(
    request: StopSessionRequest,
    client: LiveAvatarClientDep,
) -> SessionActionResponse:
    try:
        await client.stop_session(request.session_id, reason=request.reason)
        return SessionActionResponse(session_id=request.session_id, status="stopped")
    except LiveAvatarHTTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/keep-alive",
    response_model=SessionActionResponse,
    summary="Keep avatar session alive",
    description=(
        "Prevents idle timeout (LiveAvatar closes sessions after 5 min of inactivity). "
        "Call every ~3 minutes when there is no avatar activity."
    ),
)
async def keep_alive(
    request: KeepAliveRequest,
    client: LiveAvatarClientDep,
) -> SessionActionResponse:
    try:
        await client.keep_alive(request.session_id)
        return SessionActionResponse(session_id=request.session_id, status="alive")
    except LiveAvatarHTTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/speak",
    response_model=SpeakResponse,
    summary="Synthesize text into LiveAvatar-ready PCM audio",
    description=(
        "Backend-owned TTS step. Calls OpenAI TTS with response_format=pcm "
        "(24 kHz / 16-bit / mono — exactly the format LiveAvatar's `agent.speak` "
        "WebSocket event expects). The frontend chunks the returned base64 into "
        "≤1 s frames and pushes them through the /ws/avatar bridge."
    ),
)
async def speak(
    request: SpeakRequest,
    use_case: SpeakUseCaseDep,
) -> SpeakResponse:
    try:
        result = await use_case.execute(SpeakCommand(text=request.text, voice=request.voice))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenAITTSError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI TTS failed: {exc.detail}") from exc

    return SpeakResponse(
        audio_b64=result.audio_b64,
        sample_rate=result.sample_rate,
        duration_ms=result.duration_ms,
    )
