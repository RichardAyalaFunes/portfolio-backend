"""ArchiveApplication use case -- handler implementation (soft delete via archived_at)."""

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.value_objects import ApplicationId
from backend.domain.shared.errors import NotFoundError

from .command import ArchiveApplicationCommand
from .port import IArchiveApplicationUseCase
from .response import ArchiveApplicationResponse


class ArchiveApplicationHandler(IArchiveApplicationUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: ArchiveApplicationCommand) -> ArchiveApplicationResponse:
        application_id = ApplicationId.from_string(command.application_id)
        application = await self._repository.get(application_id)
        if application is None:
            raise NotFoundError(f"No application with id {command.application_id}")

        application.archive()
        await self._repository.update(application)
        return ArchiveApplicationResponse(application_id=command.application_id)
