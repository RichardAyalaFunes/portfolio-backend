"""GetKnowledgeIndex use case -- handler implementation.

The whole library as light summary rows (no bodies). The dashboard loads this once and does the
browsing, grouping and as-you-type filtering on the client.
"""

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository

from .command import GetKnowledgeIndexCommand
from .port import IGetKnowledgeIndexUseCase
from .response import GetKnowledgeIndexResponse


class GetKnowledgeIndexHandler(IGetKnowledgeIndexUseCase):
    def __init__(self, repository: IKnowledgeRepository) -> None:
        self._repository = repository

    async def execute(self, command: GetKnowledgeIndexCommand) -> GetKnowledgeIndexResponse:
        return GetKnowledgeIndexResponse(pages=await self._repository.list_summaries())
