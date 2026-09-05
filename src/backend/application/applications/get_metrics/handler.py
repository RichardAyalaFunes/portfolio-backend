"""GetMetrics use case -- handler implementation.

Aggregation happens in Python over the small in-memory working set (233 rows
today), not via SQL GROUP BY -- see docs/job-dashboard-plan.md, PostgREST
doesn't do arbitrary aggregation and a Postgres RPC function would be
over-engineering at this scale.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import Status

from .command import GetMetricsCommand
from .port import IGetMetricsUseCase
from .response import MetricsResponse


def _in_scope(applications: list[JobApplication], scope: str) -> list[JobApplication]:
    if scope == "all" or not scope:
        return applications
    if scope == "latest":
        run_dates = [a.run_date for a in applications if a.run_date]
        if not run_dates:
            return []
        target = max(run_dates)
        return [a for a in applications if a.run_date == target]
    if scope == "week":
        cutoff = date.today() - timedelta(days=7)
        return [a for a in applications if a.run_date and a.run_date >= cutoff]
    if scope.startswith("run:"):
        target = date.fromisoformat(scope[4:])
        return [a for a in applications if a.run_date == target]
    return applications


class GetMetricsHandler(IGetMetricsUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: GetMetricsCommand) -> MetricsResponse:
        applications = _in_scope(await self._repository.list(include_archived=False), command.scope)

        status_counts = Counter(a.status.value for a in applications)
        stage_counts = Counter(a.application_stage.value for a in applications)
        drop_reasons = Counter(a.drop_reason for a in applications if a.drop_reason)

        funnel_by_group: dict[str, Counter] = defaultdict(Counter)
        for a in applications:
            funnel_by_group[a.group or "unknown"][a.status.value] += 1

        portal_yield: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "approved": 0})
        for a in applications:
            bucket = portal_yield[a.source or "unknown"]
            bucket["total"] += 1
            if a.status == Status.APPROVED:
                bucket["approved"] += 1

        return MetricsResponse(
            total=len(applications),
            status_counts=dict(status_counts),
            stage_counts=dict(stage_counts),
            funnel_by_group={group: dict(counts) for group, counts in funnel_by_group.items()},
            drop_reasons=dict(drop_reasons),
            portal_yield=dict(portal_yield),
        )
