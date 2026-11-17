"""SplitPosting use case -- handler implementation.

Ingest folds a posting into a row when company and title match, which is right almost
always and wrong for a role that merely shares a title (a second opening, another team).
This undoes one such merge: the chosen posting leaves the row and becomes a row of its
own, back in the review queue. Nothing of Richard's moves with it: his notes, review
stamp and application stage stay with the original row, which was the role he judged.
"""

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications import returns
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId, Status
from backend.domain.shared.errors import InvalidValueError, NotFoundError

from .command import SplitPostingCommand
from .port import ISplitPostingUseCase
from .response import SplitPostingResponse


class SplitPostingHandler(ISplitPostingUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: SplitPostingCommand) -> SplitPostingResponse:
        application = await self._repository.get(ApplicationId.from_string(command.application_id))
        if application is None:
            raise NotFoundError(f"No application with id {command.application_id}")

        posting = next((p for p in application.postings if str(p.get("id")) == command.posting_id), None)
        if posting is None:
            raise NotFoundError(f"Application {command.application_id} has no posting {command.posting_id}")
        if len(application.postings) < 2:
            raise InvalidValueError("The only posting of a role cannot be split off")

        seen = posting.get("run_date") or application.last_seen
        created = JobApplication(
            id=ApplicationId.generate(),
            # identity_key is unique per row; the suffix keeps this row apart, and a
            # posting-id match still finds it when the same ad is seen again.
            identity_key=f"{application.identity_key}::split::{command.posting_id}",
            title=application.title,
            company=application.company,
            group=application.group,
            score=application.score,
            band=application.band,
            status=Status.TO_VALIDATE,
            location_text=application.location_text,
            work_mode=application.work_mode,
            employment_type=application.employment_type,
            salary_text=application.salary_text,
            posted_date=posting.get("posted_date") or application.posted_date,
            eligibility_text=application.eligibility_text,
            requirements_excerpt=application.requirements_excerpt,
            jd_url=posting.get("url") or application.jd_url,
            source=posting.get("source") or application.source,
            run_date=posting.get("run_date") or application.run_date,
            first_seen=seen,
            last_seen=seen,
            live_state=posting.get("live_state"),
            postings=[posting],
            discovery_queries=list(application.discovery_queries),
            tags=list(application.tags),
            extras={"split_from": str(application.id)},
        )

        application.postings = [p for p in application.postings if str(p.get("id")) != command.posting_id]
        history = [e for e in returns.returns_of(application.extras) if str(e.get("posting_id")) != command.posting_id]
        extras = dict(application.extras)
        if history:
            extras["returns"] = history
        else:
            extras.pop("returns", None)
        application.extras = extras

        created = await self._repository.create(created)
        original = await self._repository.update(application)
        return SplitPostingResponse(original=original, created=created)
