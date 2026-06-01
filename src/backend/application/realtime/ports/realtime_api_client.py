"""Driven port — interface for the OpenAI Realtime API client."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EphemeralKeyResult:
    client_secret: str
    expires_at: int = 0


class IRealtimeAPIClient(ABC):
    """Driven port for creating OpenAI Realtime ephemeral sessions."""

    @abstractmethod
    async def create_ephemeral_session(
        self, *, model: str, voice: str
    ) -> EphemeralKeyResult: ...
