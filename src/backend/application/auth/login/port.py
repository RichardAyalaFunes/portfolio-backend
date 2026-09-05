"""Login use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import LoginCommand
from .response import LoginResponse


class ILoginUseCase(ABC):
    @abstractmethod
    async def execute(self, command: LoginCommand) -> LoginResponse: ...
