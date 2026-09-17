"""UpdateContactStage use case -- handler implementation."""

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.value_objects import ApplicationId
from backend.domain.shared.errors import NotFoundError

from .command import UpdateContactStageCommand
from .port import IUpdateContactStageUseCase
from .response import UpdateContactStageResponse


class UpdateContactStageHandler(IUpdateContactStageUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: UpdateContactStageCommand) -> UpdateContactStageResponse:
        application_id = ApplicationId.from_string(command.application_id)
        application = await self._repository.get(application_id)
        if application is None:
            raise NotFoundError(f"No application with id {command.application_id}")

        if not application.update_contact_stage(command.contact_id, command.stage):
            raise NotFoundError(
                f"No contact {command.contact_id!r} on application {command.application_id}"
            )

        updated = await self._repository.update(application)
        return UpdateContactStageResponse(application=updated)
