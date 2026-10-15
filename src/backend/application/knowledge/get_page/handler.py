"""GetKnowledgePage use case -- handler implementation.

Backlinks are computed at read time from the stored outgoing `links` of every page, so they are
right the moment any page is published and never need a re-publish of the pages that are linked to.
"""

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository
from backend.domain.shared.errors import NotFoundError

from .command import GetKnowledgePageCommand
from .port import IGetKnowledgePageUseCase
from .response import GetKnowledgePageResponse


class GetKnowledgePageHandler(IGetKnowledgePageUseCase):
    def __init__(self, repository: IKnowledgeRepository) -> None:
        self._repository = repository

    async def execute(self, command: GetKnowledgePageCommand) -> GetKnowledgePageResponse:
        page = await self._repository.get(command.slug)
        if page is None:
            raise NotFoundError(f"no knowledge page {command.slug!r}")
        backlinks = await self._repository.backlinks(command.slug)
        return GetKnowledgePageResponse(page=page, backlinks=backlinks)
