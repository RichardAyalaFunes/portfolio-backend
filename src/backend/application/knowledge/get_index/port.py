"""GetKnowledgeIndex use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetKnowledgeIndexCommand
from .response import GetKnowledgeIndexResponse


class IGetKnowledgeIndexUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetKnowledgeIndexCommand) -> GetKnowledgeIndexResponse: ...
