"""PruneKnowledgePages use case -- handler implementation.

The publisher sends the slugs of every note that exists in the vault after a full publish; pages
that are stored but not in that list were deleted or renamed in the vault and are removed here.

Safety rail: a list that would remove more than half of a library of ten or more pages is refused.
That is what a truncated or wrongly filtered publish looks like, and it should not be able to wipe
the library. A real clear-out can be done in steps.
"""

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository
from backend.domain.knowledge.page import SLUG_RE
from backend.domain.shared.errors import InvalidValueError

from .command import PruneKnowledgePagesCommand
from .port import IPruneKnowledgePagesUseCase
from .response import PruneKnowledgePagesResponse

DELETE_CHUNK = 40


class PruneKnowledgePagesHandler(IPruneKnowledgePagesUseCase):
    def __init__(self, repository: IKnowledgeRepository) -> None:
        self._repository = repository

    async def execute(self, command: PruneKnowledgePagesCommand) -> PruneKnowledgePagesResponse:
        if not command.keep:
            raise InvalidValueError("keep must list the slugs to keep; an empty list would remove everything")
        for slug in command.keep:
            if not isinstance(slug, str) or not SLUG_RE.match(slug):
                raise InvalidValueError(f"{slug!r} is not a valid page slug")

        keep = set(command.keep)
        stored = await self._repository.list_slugs()
        stale = sorted(slug for slug in stored if slug not in keep)
        if len(stored) >= 10 and len(stale) * 2 > len(stored):
            raise InvalidValueError(
                f"refusing to remove {len(stale)} of {len(stored)} pages; publish the whole library first"
            )

        for start in range(0, len(stale), DELETE_CHUNK):
            await self._repository.delete(stale[start : start + DELETE_CHUNK])
        return PruneKnowledgePagesResponse(removed=len(stale))
