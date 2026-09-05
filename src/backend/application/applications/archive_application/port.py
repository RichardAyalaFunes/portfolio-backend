"""ArchiveApplication use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import ArchiveApplicationCommand
from .response import ArchiveApplicationResponse


class IArchiveApplicationUseCase(ABC):
    @abstractmethod
    async def execute(self, command: ArchiveApplicationCommand) -> ArchiveApplicationResponse: ...
