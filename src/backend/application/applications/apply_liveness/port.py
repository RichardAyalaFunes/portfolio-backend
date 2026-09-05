"""ApplyLiveness use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import ApplyLivenessCommand
from .response import ApplyLivenessResponse


class IApplyLivenessUseCase(ABC):
    @abstractmethod
    async def execute(self, command: ApplyLivenessCommand) -> ApplyLivenessResponse: ...
