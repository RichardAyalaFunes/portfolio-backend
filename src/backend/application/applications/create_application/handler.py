"""CreateApplication use case -- handler implementation.

Runs the same identity match ingest.js uses before inserting, so a manual
add of a role that's already tracked is refused rather than duplicated.
"""

from backend.application.applications.errors import DuplicateApplicationError
from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications import identity
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId, Status

from .command import CreateApplicationCommand
from .port import ICreateApplicationUseCase
from .response import CreateApplicationResponse


class CreateApplicationHandler(ICreateApplicationUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: CreateApplicationCommand) -> CreateApplicationResponse:
        existing = await self._repository.list(include_archived=False)
        candidate = {"company": command.company, "title": command.title}
        match = identity.find_match(candidate, [a.as_match_candidate() for a in existing])
        if match is not None:
            raise DuplicateApplicationError(existing_id=str(match.role["id"]))

        application = JobApplication(
            id=ApplicationId.generate(),
            identity_key=identity.identity_key(candidate),
            title=command.title,
            company=command.company,
            group=command.group,
            jd_url=command.jd_url,
            status=Status(command.status),
            source="manual",
        )
        created = await self._repository.create(application)
        return CreateApplicationResponse(application=created)
