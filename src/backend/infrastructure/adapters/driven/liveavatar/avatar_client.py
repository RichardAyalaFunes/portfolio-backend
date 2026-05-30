"""
LiveAvatarClient — driven adapter implementing IAvatarAPIClient.

Calls the LiveAvatar REST API v1 using a shared httpx.AsyncClient
(constructed by the FastAPI lifespan and injected via DI).

Authentication scheme (per LiveAvatar docs):
  - /sessions/token, /sessions/stop, /sessions/keep-alive  →  X-API-KEY header
  - /sessions/start                                         →  Authorization: Bearer <session_token>

All non-2xx responses raise LiveAvatarHTTPError; the master API key is
never written to logs or returned in responses.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.application.avatar.ports.avatar_api_client import (
    CreateTokenResult,
    IAvatarAPIClient,
    StartSessionResult,
)

logger = logging.getLogger(__name__)


class LiveAvatarHTTPError(Exception):
    """Raised when the LiveAvatar API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"LiveAvatar API error {status_code}: {detail}")


_QUOTA_STATUS_CODES: frozenset[int] = frozenset({402, 429})
"""HTTP status codes that indicate a key has exhausted its session quota."""


class LiveAvatarClient(IAvatarAPIClient):
    """
    Concrete adapter for the LiveAvatar REST API v1.

    Receives a long-lived httpx.AsyncClient. The lifespan in main.py is
    responsible for opening and closing the underlying client.

    Multiple API keys may be supplied. `create_token` will try them in order
    and advance to the next key whenever the current one returns a quota error
    (402 or 429). Other error codes are re-raised immediately.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_keys: list[str],
        base_url: str = "https://api.liveavatar.com/v1",
    ) -> None:
        if not api_keys:
            raise ValueError("LiveAvatarClient requires at least one API key.")
        self._http = http_client
        self._api_keys = api_keys
        self._base_url = base_url.rstrip("/")

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _api_key_headers(self, api_key: str) -> dict[str, str]:
        return {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    @property
    def _primary_key(self) -> str:
        """First key — used for session-management calls (stop, keep-alive)."""
        return self._api_keys[0]

    def _bearer_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _post(
        self,
        path: str,
        json: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Perform a POST and return the parsed JSON body. Raise on non-2xx."""
        url = f"{self._base_url}{path}"
        response = await self._http.post(url, headers=headers, json=json or {})

        if not response.is_success:
            # Don't echo headers (would leak the API key) — only the response body.
            detail = response.text
            logger.error(
                "LiveAvatar API error %s POST %s: %s",
                response.status_code,
                path,
                detail,
            )
            raise LiveAvatarHTTPError(response.status_code, detail)

        try:
            return response.json()  # type: ignore[no-any-return]
        except ValueError:
            return {}

    @staticmethod
    def _unwrap(envelope: dict[str, Any]) -> dict[str, Any]:
        """
        LiveAvatar wraps successful responses in {code, message, data:{…}}.
        Tolerate both wrapped and flat shapes — a few endpoints return flat.
        """
        if isinstance(envelope, dict) and "data" in envelope and isinstance(envelope["data"], dict):
            return envelope["data"]
        return envelope

    # ── Port implementation ──────────────────────────────────────────────────

    async def create_token(
        self,
        avatar_id: str,
        voice_id: str,
        context_id: str | None = None,
        language: str = "en",
        mode: str = "FULL",
        is_sandbox: bool = True,
        max_session_duration: int = 1200,
    ) -> CreateTokenResult:
        """
        POST /v1/sessions/token — create a FULL or LITE mode session token.

        Tries each configured API key in order. If a key returns a quota error
        (402 or 429) it is skipped and the next key is tried. Any other HTTP
        error is re-raised immediately. Raises LiveAvatarHTTPError(503) when
        all keys are exhausted.
        """
        avatar_persona: dict[str, Any] = {
            "voice_id": voice_id,
            "language": language,
        }
        if context_id:
            avatar_persona["context_id"] = context_id

        payload: dict[str, Any] = {
            "mode": mode,
            "avatar_id": avatar_id,
            "avatar_persona": avatar_persona,
            "is_sandbox": is_sandbox,
            "max_session_duration": max_session_duration,
        }

        last_error: LiveAvatarHTTPError | None = None
        for index, api_key in enumerate(self._api_keys):
            try:
                body = await self._post("/sessions/token", payload, self._api_key_headers(api_key))
            except LiveAvatarHTTPError as exc:
                if exc.status_code in _QUOTA_STATUS_CODES:
                    logger.warning(
                        "API key #%d quota exhausted (%s) — trying next key.",
                        index + 1,
                        exc.status_code,
                    )
                    last_error = exc
                    continue
                raise

            data = self._unwrap(body)
            try:
                session_id = data["session_id"]
                session_token = data["session_token"]
            except KeyError as exc:
                raise LiveAvatarHTTPError(
                    502, f"Unexpected token response shape: missing {exc.args[0]}"
                ) from exc

            logger.info(
                "LiveAvatar token created via key #%d (session_id=%s, sandbox=%s)",
                index + 1,
                session_id,
                is_sandbox,
            )
            return CreateTokenResult(session_id=session_id, session_token=session_token)

        raise last_error or LiveAvatarHTTPError(503, "All LiveAvatar API keys are exhausted.")

    async def start_session(self, session_token: str) -> StartSessionResult:
        """POST /v1/sessions/start — activate the session (Bearer auth)."""
        body = await self._post("/sessions/start", None, self._bearer_headers(session_token))
        data = self._unwrap(body)

        try:
            return StartSessionResult(
                session_id=data["session_id"],
                livekit_url=data.get("livekit_url", ""),
                livekit_client_token=data.get("livekit_client_token", ""),
                ws_url=data.get("ws_url", ""),
                max_session_duration=int(data.get("max_session_duration", 0) or 0),
            )
        except KeyError as exc:
            raise LiveAvatarHTTPError(
                502, f"Unexpected start response shape: missing {exc.args[0]}"
            ) from exc

    async def stop_session(self, session_id: str, reason: str = "USER_CLOSED") -> None:
        """POST /v1/sessions/stop — release the session and stop billing."""
        await self._post(
            "/sessions/stop",
            {"session_id": session_id, "reason": reason},
            self._api_key_headers(self._primary_key),
        )
        logger.info("LiveAvatar session stopped: session_id=%s reason=%s", session_id, reason)

    async def keep_alive(self, session_id: str) -> None:
        """POST /v1/sessions/keep-alive — prevent idle timeout (5 min window)."""
        await self._post(
            "/sessions/keep-alive",
            {"session_id": session_id},
            self._api_key_headers(self._primary_key),
        )
        logger.debug("LiveAvatar keep-alive sent: session_id=%s", session_id)
