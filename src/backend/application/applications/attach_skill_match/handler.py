"""AttachSkillMatch use case -- handler implementation.

The job-search agent writes one skill-match table per analysed role. This is an
agent write, not a human review: it never calls mark_reviewed(), so GET /feedback
keeps telling Richard's decisions apart from the agent's own output.

Per item: resolve the role (`application_id`, then `jd_url`), then validate and
normalise the payload. One bad item never sinks the batch: an unresolvable item goes
to `unmatched`, an item whose payload fails validation goes to `invalid` with the
reason, and the others still apply. `skill_match` None or {} clears the table.

The write touches the skill_match column only (save_skill_match), never the whole row:
the roles were read once at the start, and a batch can run for a while, during which
Richard may save a status, stage or note on one of them in the dashboard.
"""

from typing import Any

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.resolve import RoleResolver, identifier_of
from backend.domain.applications.skill_match import normalize_skill_match
from backend.domain.shared.errors import InvalidValueError

from .command import AttachSkillMatchCommand
from .port import IAttachSkillMatchUseCase
from .response import AttachSkillMatchResponse


def _is_clear_request(skill_match: Any) -> bool:
    # Only None and an empty object clear. A falsy non-object ([], "", 0) is a
    # malformed payload and must be reported, not treated as "clear".
    return skill_match is None or (isinstance(skill_match, dict) and not skill_match)


class AttachSkillMatchHandler(IAttachSkillMatchUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: AttachSkillMatchCommand) -> AttachSkillMatchResponse:
        existing = await self._repository.list(include_archived=False)
        resolver = RoleResolver(existing)

        matched = updated = 0
        unmatched: list[str] = []
        invalid: list[str] = []

        for item in command.items:
            identifier = identifier_of(item.application_id, item.jd_url)
            application = resolver.resolve(application_id=item.application_id, jd_url=item.jd_url)
            if application is None:
                unmatched.append(identifier)
                continue
            matched += 1

            try:
                payload = {} if _is_clear_request(item.skill_match) else normalize_skill_match(item.skill_match)
            except InvalidValueError as exc:
                invalid.append(f"{identifier}: {exc}")
                continue

            application.set_skill_match(payload)
            await self._repository.save_skill_match(application)
            updated += 1

        return AttachSkillMatchResponse(matched=matched, updated=updated, unmatched=unmatched, invalid=invalid)
