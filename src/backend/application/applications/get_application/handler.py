"""GetApplication use case -- handler implementation."""

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.value_objects import ApplicationId
from backend.domain.shared.errors import NotFoundError

from .command import GetApplicationCommand
from .port import IGetApplicationUseCase
from .response import GetApplicationResponse


class GetApplicationHandler(IGetApplicationUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: GetApplicationCommand) -> GetApplicationResponse:
        application_id = ApplicationId.from_string(command.application_id)
        application = await self._repository.get(application_id)
        if application is None:
            raise NotFoundError(f"No application with id {command.application_id}")
        return GetApplicationResponse(application=application)
