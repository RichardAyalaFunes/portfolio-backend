"""GetRules use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetRulesCommand
from .response import GetRulesResponse


class IGetRulesUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetRulesCommand) -> GetRulesResponse: ...
