"""PublishKnowledgePages use case -- handler implementation.

All-or-nothing: every page in the batch is validated first, and one invalid page rejects the whole
request with the reason (the publisher fixes the note and sends again). Publishing is an upsert by
slug, so sending the same pages twice changes nothing.
"""

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository
from backend.domain.knowledge.page import KnowledgePage
from backend.domain.shared.errors import InvalidValueError

from .command import PublishKnowledgePagesCommand
from .port import IPublishKnowledgePagesUseCase
from .response import PublishKnowledgePagesResponse

MAX_PAGES_PER_REQUEST = 60


class PublishKnowledgePagesHandler(IPublishKnowledgePagesUseCase):
    def __init__(self, repository: IKnowledgeRepository) -> None:
        self._repository = repository

    async def execute(self, command: PublishKnowledgePagesCommand) -> PublishKnowledgePagesResponse:
        if not command.pages:
            raise InvalidValueError("pages must not be empty")
        if len(command.pages) > MAX_PAGES_PER_REQUEST:
            raise InvalidValueError(f"at most {MAX_PAGES_PER_REQUEST} pages per request, got {len(command.pages)}")

        pages = [KnowledgePage.from_document(document) for document in command.pages]
        slugs = [page.slug for page in pages]
        if len(set(slugs)) != len(slugs):
            raise InvalidValueError("the same slug appears twice in one request")

        await self._repository.upsert(pages)
        return PublishKnowledgePagesResponse(upserted=len(pages))
