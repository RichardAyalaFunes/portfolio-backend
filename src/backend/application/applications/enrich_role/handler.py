"""EnrichRole use case -- handler implementation.

Matching order per item: `application_id` first (exact, the cheap case -- the
agent already knows the id from publishing or reading the role), then the same
LinkedIn-id-from-URL / exact-URL fallback annotate.py uses for `jd_url`. An
item matching nothing is reported in `unmatched`, never silently dropped.
"""

import re

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.entities.job_application import JobApplication

from .command import EnrichRoleCommand, EnrichRoleItem
from .port import IEnrichRoleUseCase
from .response import EnrichRoleResponse

_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)|currentJobId=(\d+)")


def _extract_id(url: str) -> str | None:
    match = _LINKEDIN_ID_RE.search(url)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _find_by_url(url: str, existing: list[JobApplication]) -> JobApplication | None:
    candidate_id = _extract_id(url)
    if candidate_id:
        for application in existing:
            if str(application.id) == candidate_id or any(
                str(p.get("id")) == candidate_id for p in application.postings
            ):
                return application
    for application in existing:
        if application.jd_url == url or any(p.get("url") == url for p in application.postings):
            return application
    return None


class EnrichRoleHandler(IEnrichRoleUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: EnrichRoleCommand) -> EnrichRoleResponse:
        existing = await self._repository.list(include_archived=False)
        by_id = {str(a.id): a for a in existing}

        matched = updated = 0
        unmatched: list[str] = []

        for item in command.items:
            application = self._resolve(item, by_id, existing)
            if application is None:
                unmatched.append(item.application_id or item.jd_url or "(no identifier)")
                continue
            matched += 1

            changed = False
            if item.contacts is not None:
                application.set_contacts(item.contacts)
                changed = True
            if item.application_form is not None:
                application.set_application_form(item.application_form)
                changed = True

            if changed:
                await self._repository.update(application)
                updated += 1

        return EnrichRoleResponse(matched=matched, updated=updated, unmatched=unmatched)

    @staticmethod
    def _resolve(
        item: EnrichRoleItem,
        by_id: dict[str, JobApplication],
        existing: list[JobApplication],
    ) -> JobApplication | None:
        if item.application_id and item.application_id in by_id:
            return by_id[item.application_id]
        if item.jd_url:
            return _find_by_url(item.jd_url, existing)
        return None
