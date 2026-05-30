"""GenerateToken use case — response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerateTokenResponse:
    """
    Result of the GenerateToken use case.

    session_id:    LiveAvatar's internal session identifier.
    session_token: Short-lived JWT used by the frontend to call /sessions/start.

    Note: ws_url and the LiveKit room credentials are NOT returned here.
    Per LiveAvatar docs they come from POST /v1/sessions/start, which is
    a separate use case (see StartSessionResult).
    """

    session_id: str
    session_token: str
