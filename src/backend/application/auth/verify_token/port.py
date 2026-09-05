"""VerifyToken use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import VerifyTokenCommand
from .response import VerifyTokenResponse


class IVerifyTokenUseCase(ABC):
    @abstractmethod
    async def execute(self, command: VerifyTokenCommand) -> VerifyTokenResponse: ...
