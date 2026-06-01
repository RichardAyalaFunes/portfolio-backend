"""
Realtime REST controller — driver adapter (inbound).

Exposes a single endpoint that mints an OpenAI Realtime ephemeral key
so the browser can open a WebRTC session without exposing the master
API key.
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from backend.application.realtime.create_session.command import (
    CreateRealtimeSessionCommand,
)
from backend.application.realtime.create_session.port import (
    ICreateRealtimeSessionUseCase,
)
from backend.infrastructure.adapters.driven.openai.openai_realtime_client import (
    OpenAIRealtimeError,
)
from backend.infrastructure.config.dependencies import (
    get_create_realtime_session_use_case,
)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


class CreateSessionRequest(BaseModel):
    voice: Optional[str] = Field(
        default=None,
        description="Override the default voice (alloy, echo, fable, onyx, nova, shimmer).",
    )


class CreateSessionResponse(BaseModel):
    client_secret: str = Field(description="Short-lived ephemeral key for WebRTC auth.")
    expires_at: int = Field(description="Unix timestamp when the key expires.")


CreateRealtimeSessionUseCaseDep = Annotated[
    ICreateRealtimeSessionUseCase,
    Depends(get_create_realtime_session_use_case),
]


@router.post(
    "/session",
    response_model=CreateSessionResponse,
    summary="Create an OpenAI Realtime ephemeral session",
    description=(
        "Calls OpenAI's /v1/realtime/sessions with the server-side API key and "
        "returns a short-lived ephemeral key. The frontend uses this key to "
        "authenticate a WebRTC peer connection directly to OpenAI."
    ),
)
async def create_session(
    request: CreateSessionRequest,
    use_case: CreateRealtimeSessionUseCaseDep,
) -> CreateSessionResponse:
    logger.info("POST /api/realtime/session voice=%s", request.voice or "default")
    try:
        result = await use_case.execute(
            CreateRealtimeSessionCommand(voice=request.voice)
        )
        logger.info("Ephemeral session created successfully expires_at=%s", result.expires_at)
        return CreateSessionResponse(
            client_secret=result.client_secret,
            expires_at=result.expires_at,
        )
    except OpenAIRealtimeError as exc:
        logger.error("Failed to create realtime session status=%s detail=%s", exc.status_code, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
