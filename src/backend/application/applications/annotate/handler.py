"""Annotate use case -- handler implementation.

Ports annotate.js's core behavior: match by id extracted from the URL (falls
back to exact URL string equality against jd_url/postings urls), append the
comment to notes unless it's already there (idempotent -- re-running the same
file twice adds nothing the second time). Simplified vs. the original for
non-LinkedIn portals: Wellfound/YC id-extraction patterns aren't reproduced,
only LinkedIn's `/jobs/view/<id>` and `currentJobId=<id>` plus the exact-URL
fallback -- acceptable since 90%+ of tracked postings are LinkedIn (see
docs/job-dashboard-plan.md ss1) and the fallback still catches the rest whenever
the URL matches verbatim.
"""

import re

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.entities.job_application import JobApplication

from .command import AnnotateCommand
from .port import IAnnotateUseCase
from .response import AnnotateResponse

_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)|currentJobId=(\d+)")


def _extract_id(url: str) -> str | None:
    match = _LINKEDIN_ID_RE.search(url)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _find_role(url: str, existing: list[JobApplication]) -> JobApplication | None:
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


class AnnotateHandler(IAnnotateUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: AnnotateCommand) -> AnnotateResponse:
        existing = await self._repository.list(include_archived=False)

        added = already_present = 0
        unmatched: list[str] = []

        for item in command.items:
            application = _find_role(item.url, existing)
            if application is None:
                unmatched.append(item.url)
                continue

            if item.note.lower() in application.notes.lower():
                already_present += 1
                continue

            application.update_notes(
                f"{application.notes} | {item.note}" if application.notes else item.note
            )
            await self._repository.update(application)
            added += 1

        return AnnotateResponse(added=added, already_present=already_present, unmatched=unmatched)
