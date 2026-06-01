"""CreateRealtimeSession use case — response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateRealtimeSessionResponse:
    client_secret: str
    expires_at: int
