"""GetMetrics: the headline "to review" count follows the queue's rule, not the raw status
count, and the per-scope behaviour the dashboard already relied on keeps working."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.application.applications.get_metrics.command import GetMetricsCommand
from backend.application.applications.get_metrics.handler import GetMetricsHandler
from backend.domain.applications.value_objects import Stage, Status
from tests.support.builders import make_application
from tests.support.in_memory import InMemoryApplicationRepository

TODAY = date.today()


async def metrics(repo, scope="all"):
    return await GetMetricsHandler(repository=repo).execute(GetMetricsCommand(scope=scope))


@pytest.mark.asyncio
async def test_to_review_counts_what_the_queue_calls_to_review_while_status_counts_stay_raw():
    repo = InMemoryApplicationRepository()
    repo.add(
        make_application(status=Status.TO_VALIDATE),                                          # waiting
        make_application(status=Status.TO_VALIDATE, live_state="LISTED"),                     # waiting
        make_application(status=Status.TO_VALIDATE, application_stage=Stage.APPLIED),         # applied: left the queue
        make_application(status=Status.TO_VALIDATE, live_state="CLOSED"),                     # posting closed
        make_application(status=Status.TO_VALIDATE, drop_stage="scored", drop_reason="below_bar"),  # did not pass
        make_application(status=Status.FLAGGED),
        make_application(status=Status.APPROVED),
    )

    result = await metrics(repo)

    assert result.total == 7
    assert result.to_review == 2
    assert result.status_counts["To validate"] == 5  # the raw stored status, unchanged
    assert result.stage_counts == {"Not applied": 6, "Applied": 1}


@pytest.mark.asyncio
async def test_to_review_is_zero_with_nothing_waiting_and_ignores_archived_roles():
    repo = InMemoryApplicationRepository()
    repo.add(
        make_application(status=Status.APPROVED),
        make_application(status=Status.TO_VALIDATE, archived_at=datetime(2026, 9, 30, tzinfo=timezone.utc)),
    )

    result = await metrics(repo)

    assert (result.total, result.to_review) == (1, 0)


@pytest.mark.asyncio
async def test_to_review_respects_the_scope_like_every_other_count():
    repo = InMemoryApplicationRepository()
    repo.add(
        make_application(status=Status.TO_VALIDATE, run_date=TODAY),
        make_application(status=Status.TO_VALIDATE, run_date=TODAY - timedelta(days=30)),
    )

    assert (await metrics(repo, "all")).to_review == 2
    assert (await metrics(repo, "latest")).to_review == 1
    assert (await metrics(repo, "week")).to_review == 1
