"""UpdateApplication use case -- handler implementation."""

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.value_objects import ApplicationId, Stage, Status
from backend.domain.shared.errors import NotFoundError

from .command import UpdateApplicationCommand
from .port import IUpdateApplicationUseCase
from .response import UpdateApplicationResponse


class UpdateApplicationHandler(IUpdateApplicationUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: UpdateApplicationCommand) -> UpdateApplicationResponse:
        application_id = ApplicationId.from_string(command.application_id)
        application = await self._repository.get(application_id)
        if application is None:
            raise NotFoundError(f"No application with id {command.application_id}")

        if command.status is not None:
            application.set_status(Status(command.status))
        if command.stage is not None:
            application.set_stage(Stage(command.stage))
        if command.notes is not None:
            application.update_notes(command.notes)
        if command.jd_url is not None:
            application.jd_url = command.jd_url

        updated = await self._repository.update(application)
        return UpdateApplicationResponse(application=updated)
