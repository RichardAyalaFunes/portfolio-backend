"""PruneKnowledgePages use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import PruneKnowledgePagesCommand
from .response import PruneKnowledgePagesResponse


class IPruneKnowledgePagesUseCase(ABC):
    @abstractmethod
    async def execute(self, command: PruneKnowledgePagesCommand) -> PruneKnowledgePagesResponse: ...
