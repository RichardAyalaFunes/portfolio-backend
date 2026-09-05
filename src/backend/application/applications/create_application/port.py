"""CreateApplication use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import CreateApplicationCommand
from .response import CreateApplicationResponse


class ICreateApplicationUseCase(ABC):
    @abstractmethod
    async def execute(self, command: CreateApplicationCommand) -> CreateApplicationResponse: ...
