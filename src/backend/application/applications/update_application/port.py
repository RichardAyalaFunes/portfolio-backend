"""UpdateApplication use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import UpdateApplicationCommand
from .response import UpdateApplicationResponse


class IUpdateApplicationUseCase(ABC):
    @abstractmethod
    async def execute(self, command: UpdateApplicationCommand) -> UpdateApplicationResponse: ...
