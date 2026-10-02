"""GetRules use case -- handler implementation.

Returns the rules document the job-search agent last published, plus two stat maps
computed at read time from the roles themselves (never stored in the document, so
they cannot go stale between publishes):
  - line_stats: per search line, how many roles it surfaced and what Richard did
                with them. Same definitions as GetFeedback's query_performance
                (this reuses it), with every counter always present. Archived
                roles are included: deleting a role is a verdict on the line that
                found it.
  - lane_stats: per lane (application.group), where its live roles stand in the
                review pipeline. Archived roles are skipped: this describes the
                dashboard as Richard sees it now.

Aggregation is in Python over the in-memory working set, same as GetMetrics.
"""

from collections import defaultdict

from backend.application.applications.get_feedback.handler import _ADVANCED_STAGES, query_performance
from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.ports.search_rules_repository import ISearchRulesRepository
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import Stage, Status

from .command import GetRulesCommand
from .port import IGetRulesUseCase
from .response import GetRulesResponse

LINE_COUNTERS = ("surfaced", "approved", "rejected", "applied")
LANE_COUNTERS = ("total", "to_review", "flagged", "approved", "applied", "rejected")
UNKNOWN_LANE = "unknown"


def line_stats(applications: list[JobApplication]) -> dict[str, dict[str, int]]:
    """Per search line: surfaced / approved / rejected / applied. `approved` is status
    Approved OR an advanced stage (Applied, Interviewing, Offer); `rejected` is status
    Rejected on a role that never advanced; `applied` is an advanced stage. A role with
    no discovery_queries counts under its found_by_query, if it has one."""
    performance = query_performance(applications)
    return {line: {key: counts.get(key, 0) for key in LINE_COUNTERS} for line, counts in performance.items()}


def lane_stats(applications: list[JobApplication]) -> dict[str, dict[str, int]]:
    """Per lane, over live (non-archived) roles. `to_review` and `flagged` only count
    roles not yet applied to; `approved` and `applied` use the same advanced-stage
    rule as line_stats."""
    table: dict[str, dict[str, int]] = defaultdict(lambda: {key: 0 for key in LANE_COUNTERS})
    for application in applications:
        if application.is_archived:
            continue
        row = table[application.group or UNKNOWN_LANE]
        advanced = application.application_stage in _ADVANCED_STAGES
        not_applied = application.application_stage == Stage.NOT_APPLIED

        row["total"] += 1
        if application.status == Status.TO_VALIDATE and not_applied:
            row["to_review"] += 1
        if application.status == Status.FLAGGED and not_applied:
            row["flagged"] += 1
        if application.status == Status.APPROVED or advanced:
            row["approved"] += 1
        if advanced:
            row["applied"] += 1
        if application.status == Status.REJECTED and not advanced:
            row["rejected"] += 1
    return {lane: dict(counts) for lane, counts in sorted(table.items())}


class GetRulesHandler(IGetRulesUseCase):
    def __init__(
        self,
        rules_repository: ISearchRulesRepository,
        application_repository: IJobApplicationRepository,
    ) -> None:
        self._rules_repository = rules_repository
        self._application_repository = application_repository

    async def execute(self, command: GetRulesCommand) -> GetRulesResponse:
        stored = await self._rules_repository.get()
        applications = await self._application_repository.list(include_archived=True)
        return GetRulesResponse(
            published_at=stored["published_at"] if stored else None,
            content=stored["content"] if stored else None,
            line_stats=line_stats(applications),
            lane_stats=lane_stats(applications),
        )
