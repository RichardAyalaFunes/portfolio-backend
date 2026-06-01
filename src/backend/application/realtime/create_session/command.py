"""CreateRealtimeSession use case — command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateRealtimeSessionCommand:
    """
    Command to create an OpenAI Realtime ephemeral session.

    voice: Optional override for the default voice. None = use settings default.
    """

    voice: Optional[str] = None
