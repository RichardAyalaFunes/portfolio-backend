"""SplitPosting use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import SplitPostingCommand
from .response import SplitPostingResponse


class ISplitPostingUseCase(ABC):
    @abstractmethod
    async def execute(self, command: SplitPostingCommand) -> SplitPostingResponse: ...
