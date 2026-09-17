"""UpdateContactStage use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import UpdateContactStageCommand
from .response import UpdateContactStageResponse


class IUpdateContactStageUseCase(ABC):
    @abstractmethod
    async def execute(self, command: UpdateContactStageCommand) -> UpdateContactStageResponse: ...
