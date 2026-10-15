"""GetKnowledgePage use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetKnowledgePageCommand
from .response import GetKnowledgePageResponse


class IGetKnowledgePageUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetKnowledgePageCommand) -> GetKnowledgePageResponse: ...
