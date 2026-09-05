"""ListApplications use case -- handler implementation."""

from backend.application.applications.ports.application_repository import IJobApplicationRepository

from .command import ListApplicationsCommand
from .port import IListApplicationsUseCase
from .response import ListApplicationsResponse


class ListApplicationsHandler(IListApplicationsUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: ListApplicationsCommand) -> ListApplicationsResponse:
        applications = await self._repository.list(
            status=command.status,
            stage=command.stage,
            group=command.group,
            source=command.source,
            live_state=command.live_state,
            run_date=command.run_date,
            query=command.query,
            sort=command.sort,
        )
        return ListApplicationsResponse(applications=applications)
