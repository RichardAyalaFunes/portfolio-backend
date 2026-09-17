"""GetFeedback use case -- handler implementation.

The job-search agent's first step on every run: read what Richard decided in the
dashboard since the last run, so the run can change its search plan instead of
repeating it. Views:
  - reviewed:          every role he touched (status, stage or note) since `since`,
                       newest first, notes verbatim -- the raw feedback.
  - query_performance: ALL-TIME verdicts per search line (discovery_queries), so a
                       line is promoted or retired on its whole record, not one run.
  - disagreements:     where his verdict and the agent's score disagree -- the
                       rubric-calibration signal.
  - recent_runs:       what the last runs surfaced, passed and changed in the plan.

Aggregation is in Python over the in-memory working set, same as GetMetrics.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.ports.search_run_repository import ISearchRunRepository
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import Stage, Status

from .command import GetFeedbackCommand
from .port import IGetFeedbackUseCase
from .response import FeedbackResponse

DEFAULT_WINDOW_DAYS = 30
PASS_BAR = 75
HIGH_SCORE = 85
_ADVANCED_STAGES = (Stage.APPLIED, Stage.INTERVIEWING, Stage.OFFER)
_RUN_FIELDS = (
    "run_date", "label", "cards_surfaced", "jd_extracted", "portals", "notes",
    "outcome", "line_yield", "plan_changes",
)


def _reviewed_item(application: JobApplication) -> dict[str, Any]:
    return {
        "id": str(application.id),
        "company": application.company,
        "title": application.title,
        "status": application.status.value,
        "application_stage": application.application_stage.value,
        "archived": application.is_archived,
        "group": application.group,
        "secondary_lanes": application.secondary_lanes,
        "score": application.score,
        "band": application.band,
        "tags": application.tags,
        "source": application.source,
        "discovery_queries": application.discovery_queries,
        "location_text": application.location_text,
        "drop_reason": application.drop_reason,
        "notes": application.notes,
        "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
        "jd_url": application.jd_url,
    }


def _brief(application: JobApplication) -> dict[str, Any]:
    return {
        "id": str(application.id),
        "company": application.company,
        "title": application.title,
        "score": application.score,
        "group": application.group,
        "notes": application.notes,
    }


def _queries_of(application: JobApplication) -> list[str]:
    if application.discovery_queries:
        return application.discovery_queries
    return [application.found_by_query] if application.found_by_query else []


def query_performance(applications: list[JobApplication]) -> dict[str, dict[str, int]]:
    """Per search line: roles it surfaced and Richard's verdicts on them.
    A role he applied to counts as approved even if its status was never moved."""
    table: dict[str, Counter[str]] = defaultdict(Counter)
    for application in applications:
        advanced = application.application_stage in _ADVANCED_STAGES
        for query in _queries_of(application):
            row = table[query]
            row["surfaced"] += 1
            if application.status == Status.APPROVED or advanced:
                row["approved"] += 1
            elif application.status == Status.REJECTED:
                row["rejected"] += 1
            if advanced:
                row["applied"] += 1
    return {query: dict(counts) for query, counts in sorted(table.items())}


def disagreements(applications: list[JobApplication]) -> dict[str, list[dict[str, Any]]]:
    return {
        "approved_below_bar": [
            _brief(a) for a in applications
            if a.status == Status.APPROVED and a.score is not None and a.score < PASS_BAR
        ],
        "rejected_high_score": [
            _brief(a) for a in applications
            if a.status == Status.REJECTED and a.score is not None and a.score >= HIGH_SCORE
        ],
    }


def summarize(reviewed: list[JobApplication]) -> dict[str, Any]:
    by_lane: dict[str, Counter[str]] = defaultdict(Counter)
    tags_on_rejected: Counter[str] = Counter()
    for application in reviewed:
        by_lane[application.group or "unknown"][application.status.value] += 1
        if application.status == Status.REJECTED:
            tags_on_rejected.update(application.tags)
    return {
        "reviewed_total": len(reviewed),
        "with_notes": sum(1 for a in reviewed if a.notes),
        "by_status": dict(Counter(a.status.value for a in reviewed)),
        "by_stage": dict(Counter(a.application_stage.value for a in reviewed)),
        "by_lane": {lane: dict(counts) for lane, counts in by_lane.items()},
        "by_source": dict(Counter(a.source or "unknown" for a in reviewed)),
        "tags_on_rejected": dict(tags_on_rejected),
    }


def resolve_since(requested: date | None, runs: list[dict[str, Any]]) -> tuple[date, str]:
    """`runs` is newest first. The latest run's own date is included on purpose: a
    review made that same day, before or after the run, must not be lost."""
    if requested is not None:
        return requested, "request"
    if runs and runs[0].get("run_date"):
        return date.fromisoformat(str(runs[0]["run_date"])[:10]), "latest_run"
    return date.today() - timedelta(days=DEFAULT_WINDOW_DAYS), "default_window"


class GetFeedbackHandler(IGetFeedbackUseCase):
    def __init__(self, repository: IJobApplicationRepository, run_repository: ISearchRunRepository) -> None:
        self._repository = repository
        self._run_repository = run_repository

    async def execute(self, command: GetFeedbackCommand) -> FeedbackResponse:
        runs = await self._run_repository.list_all()
        since, since_source = resolve_since(command.since, runs)

        # Archived rows are included: Richard deleting a role is feedback too.
        applications = await self._repository.list(include_archived=True)
        reviewed = sorted(
            (a for a in applications if a.reviewed_at and a.reviewed_at.date() >= since),
            key=lambda a: a.reviewed_at,
            reverse=True,
        )
        judged = [
            a for a in applications
            if a.reviewed_at or a.status in (Status.APPROVED, Status.REJECTED)
            or a.application_stage in _ADVANCED_STAGES
        ]
        live = [a for a in applications if not a.is_archived]

        return FeedbackResponse(
            since=since,
            since_source=since_source,
            reviewed=[_reviewed_item(a) for a in reviewed],
            summary=summarize(reviewed),
            query_performance=query_performance(judged),
            disagreements=disagreements(judged),
            backlog={
                "to_validate_unreviewed": sum(
                    1 for a in live if a.status == Status.TO_VALIDATE and not a.reviewed_at
                ),
                "flagged_unreviewed": sum(
                    1 for a in live if a.status == Status.FLAGGED and not a.reviewed_at
                ),
            },
            recent_runs=[{k: run.get(k) for k in _RUN_FIELDS} for run in runs[: command.recent_runs]],
        )
