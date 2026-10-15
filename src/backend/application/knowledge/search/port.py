"""SearchKnowledge use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import SearchKnowledgeCommand
from .response import SearchKnowledgeResponse


class ISearchKnowledgeUseCase(ABC):
    @abstractmethod
    async def execute(self, command: SearchKnowledgeCommand) -> SearchKnowledgeResponse: ...
