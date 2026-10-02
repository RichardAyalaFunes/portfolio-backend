"""PublishRules use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import PublishRulesCommand
from .response import PublishRulesResponse


class IPublishRulesUseCase(ABC):
    @abstractmethod
    async def execute(self, command: PublishRulesCommand) -> PublishRulesResponse: ...
