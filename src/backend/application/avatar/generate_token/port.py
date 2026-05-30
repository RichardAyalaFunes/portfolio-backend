"""GenerateToken use case — driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GenerateTokenCommand
from .response import GenerateTokenResponse


class IGenerateTokenUseCase(ABC):
    """Driver port — interface for the GenerateToken use case."""

    @abstractmethod
    async def execute(self, command: GenerateTokenCommand) -> GenerateTokenResponse: ...
