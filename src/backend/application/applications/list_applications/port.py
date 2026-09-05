"""ListApplications use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import ListApplicationsCommand
from .response import ListApplicationsResponse


class IListApplicationsUseCase(ABC):
    @abstractmethod
    async def execute(self, command: ListApplicationsCommand) -> ListApplicationsResponse: ...
