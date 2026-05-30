"""
IAvatarAPIClient — driven port for the LiveAvatar external API.

The infrastructure layer provides the concrete implementation.
The application layer only depends on this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateTokenResult:
    """
    Result of POST /v1/sessions/token from LiveAvatar.

    Per LiveAvatar docs the token endpoint returns only session_id +
    session_token; ws_url and the LiveKit credentials come from /start.
    """

    session_id: str
    session_token: str


@dataclass(frozen=True)
class StartSessionResult:
    """
    Result of POST /v1/sessions/start from LiveAvatar.

    LiveAvatar returns:
      - session_id: same id as create_token
      - livekit_url + livekit_client_token: for the WebRTC video/audio room
      - ws_url: the LITE-mode WebSocket the developer pushes agent.speak frames to
      - max_session_duration: enforced ceiling in seconds
    """

    session_id: str
    livekit_url: str
    livekit_client_token: str
    ws_url: str
    max_session_duration: int = 0


class IAvatarAPIClient(ABC):
    """Driven port — defines the contract for calling the LiveAvatar REST API."""

    @abstractmethod
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
        Request a session token (FULL or LITE mode).

        POST /v1/sessions/token  → {code, message, data:{session_id, session_token}}
        """

    @abstractmethod
    async def start_session(self, session_token: str) -> StartSessionResult:
        """
        Start an existing session.

        POST /v1/sessions/start  (auth: Bearer <session_token>)
        """

    @abstractmethod
    async def stop_session(self, session_id: str, reason: str = "USER_CLOSED") -> None:
        """
        Stop and release a session.

        POST /v1/sessions/stop  (auth: X-API-KEY)
        """

    @abstractmethod
    async def keep_alive(self, session_id: str) -> None:
        """
        Prevent the session from timing out (5 min idle window).

        POST /v1/sessions/keep-alive  (auth: X-API-KEY)
        """
