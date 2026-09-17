"""EnrichRole use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import EnrichRoleCommand
from .response import EnrichRoleResponse


class IEnrichRoleUseCase(ABC):
    @abstractmethod
    async def execute(self, command: EnrichRoleCommand) -> EnrichRoleResponse: ...
