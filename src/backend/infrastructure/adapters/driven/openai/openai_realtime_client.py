"""
OpenAI Realtime API client — driven adapter.

Calls POST /v1/realtime/client_secrets to mint an ephemeral key that the
browser uses to authenticate a WebRTC connection directly to OpenAI.
The master API key never leaves the server.
"""

import logging

import httpx

from backend.application.realtime.ports.realtime_api_client import (
    EphemeralKeyResult,
    IRealtimeAPIClient,
)

logger = logging.getLogger(__name__)


class OpenAIRealtimeError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class OpenAIRealtimeClient(IRealtimeAPIClient):
    _BASE_URL = "https://api.openai.com/v1/realtime/client_secrets"

    def __init__(self, *, http_client: httpx.AsyncClient, api_key: str) -> None:
        self._http = http_client
        self._api_key = api_key

    async def create_ephemeral_session(
        self, *, model: str, voice: str
    ) -> EphemeralKeyResult:
        logger.info("Requesting ephemeral key from OpenAI Realtime API model=%s voice=%s", model, voice)

        response = await self._http.post(
            self._BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "session": {
                    "type": "realtime",
                    "model": model,
                    "audio": {"output": {"voice": voice}},
                }
            },
        )

        if response.status_code != 200:
            logger.error(
                "OpenAI Realtime API error status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise OpenAIRealtimeError(
                status_code=response.status_code,
                detail=response.text,
            )

        data = response.json()
        # Response shape: {"value": "ek_...", "expires_at": ...}
        # expires_at may be absent in some API versions
        logger.info("Ephemeral key issued expires_at=%s", data.get("expires_at", 0))

        return EphemeralKeyResult(
            client_secret=data["value"],
            expires_at=data.get("expires_at", 0),
        )
