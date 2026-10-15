"""PublishKnowledgePages use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import PublishKnowledgePagesCommand
from .response import PublishKnowledgePagesResponse


class IPublishKnowledgePagesUseCase(ABC):
    @abstractmethod
    async def execute(self, command: PublishKnowledgePagesCommand) -> PublishKnowledgePagesResponse: ...
