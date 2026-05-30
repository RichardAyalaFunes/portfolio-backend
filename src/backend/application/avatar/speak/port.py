"""Speak use case — driver port (interface)."""

from abc import ABC, abstractmethod

from .command import SpeakCommand
from .response import SpeakResponse


class ISpeakUseCase(ABC):
    """Driver port — interface for the Speak use case."""

    @abstractmethod
    async def execute(self, command: SpeakCommand) -> SpeakResponse: ...
