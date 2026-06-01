"""CreateRealtimeSession use case — driver port (interface)."""

from abc import ABC, abstractmethod

from .command import CreateRealtimeSessionCommand
from .response import CreateRealtimeSessionResponse


class ICreateRealtimeSessionUseCase(ABC):
    """Driver port — interface for the CreateRealtimeSession use case."""

    @abstractmethod
    async def execute(
        self, command: CreateRealtimeSessionCommand
    ) -> CreateRealtimeSessionResponse: ...
