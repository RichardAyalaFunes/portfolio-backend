"""GetApplication use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetApplicationCommand
from .response import GetApplicationResponse


class IGetApplicationUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetApplicationCommand) -> GetApplicationResponse: ...
