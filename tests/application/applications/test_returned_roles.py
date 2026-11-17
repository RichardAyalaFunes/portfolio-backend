"""A role we already hold, posted again under a new posting id: when is that a
comeback, what does it do to the stored status, and what is recorded. In-memory repo."""

from datetime import datetime, timezone

import pytest

from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from backend.domain.applications import returns
from backend.domain.applications.value_objects import Stage, Status
from tests.support.in_memory import InMemoryApplicationRepository


def role(**overrides):
    base = {
        "id": "4001",
        "title": "Applied AI Engineer",
        "company": "Acme AI",
        "group": "ai_engineer",
        "score": 82,
        "jd_url": "https://www.linkedin.com/jobs/view/4001",
        "source": "linkedin",
        "run_date": "2026-09-17",
    }
    base.update(overrides)
    return base


async def ingest(repo, *roles):
    return await IngestBatchHandler(repository=repo).execute(IngestBatchCommand(roles=list(roles)))


async def only(repo):
    rows = [a for a in await repo.list(include_archived=False) if a.company == "Acme AI"]
    assert len(rows) == 1
    return rows[0]


async def seed(repo, *, first_run="2026-09-17", status=None, reviewed=False, stage=None, **role_fields):
    """Acme AI first seen on `first_run`, plus a different company seen midway so that a
    search demonstrably ran in between. Then the row is put in the state under test."""
    await ingest(repo, role(run_date=first_run, **role_fields))
    await ingest(repo, role(id="9001", title="Other", company="Other Co", run_date="2026-10-10"))
    row = await only(repo)
    if status is not None:
        row.status = status
    if stage is not None:
        row.application_stage = stage
    if reviewed:
        row.reviewed_at = datetime(2026, 10, 12, tzinfo=timezone.utc)
    row.notes = "my note"
    await repo.update(row)


def again(**overrides):
    return role(id="5002", jd_url="https://www.linkedin.com/jobs/view/5002", run_date="2026-11-16", **overrides)


# ---- the thresholds ----------------------------------------------------------

@pytest.mark.parametrize("gap, kind", [(7, "reposted"), (35, "reposted"), (90, "reposted"), (91, "reopened"), (144, "reopened")])
def test_classify_thresholds(gap, kind):
    assert returns.classify(gap=gap, is_new_posting=True, searched_between=True) == kind


@pytest.mark.parametrize("gap", [0, 3, 6])
def test_under_a_week_is_the_same_ad(gap):
    assert returns.classify(gap=gap, is_new_posting=True, searched_between=True) is None


def test_same_posting_id_is_never_a_comeback():
    assert returns.classify(gap=200, is_new_posting=False, searched_between=True) is None


def test_no_search_in_between_is_not_a_comeback():
    assert returns.classify(gap=40, is_new_posting=True, searched_between=False) is None


# ---- end to end through the ingest handler -----------------------------------

@pytest.mark.asyncio
async def test_rejected_role_that_is_reposted_returns_to_validate_and_remembers_the_rejection():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.REJECTED, reviewed=True)

    result = await ingest(repo, again())

    row = await only(repo)
    assert row.status == Status.TO_VALIDATE
    assert row.notes == "my note"          # his words survive
    assert row.reviewed_at is not None     # and so does the review stamp
    (event,) = row.extras["returns"]
    assert event["kind"] == "reposted"
    assert event["gap_days"] == 60
    assert event["prior"]["status"] == "Rejected"
    assert event["prior"]["decided_by"] == "you"
    assert event["status_reset"] is True
    assert event["posting_id"] == "5002"
    assert [r["kind"] for r in result.returned] == ["reposted"]
    assert result.returned[0]["status_reset"] is True


@pytest.mark.asyncio
async def test_agent_dropped_role_reopened_months_later_is_attributed_to_the_agent():
    repo = InMemoryApplicationRepository()
    await seed(repo, first_run="2026-06-25", status=Status.DROPPED, drop_reason="deal_breaker")

    await ingest(repo, again(salary_text="USD 6-8k"))

    row = await only(repo)
    (event,) = row.extras["returns"]
    assert event["kind"] == "reopened"
    assert event["prior"]["decided_by"] == "agent"
    assert event["prior"]["drop_reason"] == "deal_breaker"
    assert event["changes"]["salary_text"] == [None, "USD 6-8k"]
    assert row.status == Status.TO_VALIDATE
    assert row.salary_text == "USD 6-8k"     # facts of the new posting replace the old
    assert row.drop_reason is None           # the old drop reason no longer applies


@pytest.mark.asyncio
async def test_a_new_posting_the_same_week_is_not_a_comeback():
    repo = InMemoryApplicationRepository()
    await seed(repo, first_run="2026-11-12", status=Status.REJECTED, reviewed=True)

    result = await ingest(repo, again())

    row = await only(repo)
    assert "returns" not in row.extras
    assert row.status == Status.REJECTED
    assert result.returned == []


@pytest.mark.asyncio
async def test_same_posting_id_found_again_changes_nothing():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.REJECTED, reviewed=True)

    result = await ingest(repo, role(run_date="2026-11-16"))

    row = await only(repo)
    assert row.status == Status.REJECTED
    assert "returns" not in row.extras
    assert result.returned == []


@pytest.mark.asyncio
async def test_no_search_between_the_dates_means_the_role_never_went_away():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role(run_date="2026-09-17"))
    row = await only(repo)
    row.status = Status.REJECTED
    await repo.update(row)

    result = await ingest(repo, again())     # nothing else was ever uploaded in between

    assert result.returned == []
    assert (await only(repo)).status == Status.REJECTED


@pytest.mark.asyncio
async def test_approved_role_is_recorded_but_not_reset():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.APPROVED, reviewed=True)

    result = await ingest(repo, again())

    row = await only(repo)
    assert row.status == Status.APPROVED
    assert row.extras["returns"][0]["status_reset"] is False
    assert result.returned[0]["status_reset"] is False


@pytest.mark.asyncio
async def test_role_he_applied_to_raises_an_alert_and_keeps_its_status():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.REJECTED, reviewed=True, stage=Stage.INTERVIEWING)

    result = await ingest(repo, again())

    row = await only(repo)
    assert row.status == Status.REJECTED
    assert row.application_stage == Stage.INTERVIEWING
    assert result.returned[0]["alert"] == "applied_before"
    assert row.extras["returns"][0]["prior"]["application_stage"] == "Interviewing"


@pytest.mark.asyncio
async def test_if_the_new_posting_is_scored_dropped_again_the_old_status_stays():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.REJECTED, reviewed=True)

    await ingest(repo, again(status="Dropped", drop_reason="below_bar"))

    row = await only(repo)
    assert row.status == Status.REJECTED
    assert row.extras["returns"][0]["status_reset"] is False


@pytest.mark.asyncio
async def test_evergreen_role_stops_resurfacing_after_three_comebacks():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.DROPPED)
    row = await only(repo)
    row.extras = {"returns": [{"kind": "reposted"}, {"kind": "reposted"}, {"kind": "reposted"}]}
    await repo.update(row)

    result = await ingest(repo, again())

    row = await only(repo)
    assert row.status == Status.DROPPED
    assert len(row.extras["returns"]) == 4
    assert result.returned[0]["evergreen"] is True
    assert result.returned[0]["status_reset"] is False


@pytest.mark.asyncio
async def test_a_role_still_waiting_gets_the_tag_without_a_status_change():
    repo = InMemoryApplicationRepository()
    await seed(repo, status=Status.TO_VALIDATE)

    await ingest(repo, again())

    row = await only(repo)
    assert row.status == Status.TO_VALIDATE
    assert row.extras["returns"][0]["status_reset"] is False
