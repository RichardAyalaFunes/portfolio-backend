"""Rejecting a role because it duplicates another one: stored as a reason on a Rejected
role, invisible to the taste signals the search agent learns from, and never resurfaced
by a repost."""

import pytest

from backend.application.applications.get_feedback.handler import disagreements, query_performance, summarize
from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from backend.application.applications.update_application.command import UpdateApplicationCommand
from backend.application.applications.update_application.handler import UpdateApplicationHandler
from backend.domain.applications.value_objects import Status
from backend.domain.shared.errors import InvalidValueError
from tests.support.builders import make_application
from tests.support.in_memory import InMemoryApplicationRepository


async def update(repo, application, **fields):
    return await UpdateApplicationHandler(repository=repo).execute(
        UpdateApplicationCommand(application_id=str(application.id), **fields)
    )


@pytest.mark.asyncio
async def test_a_duplicate_is_a_rejection_with_a_reason_and_counts_as_reviewed():
    repo = InMemoryApplicationRepository()
    role = make_application()
    repo.add(role)

    result = await update(repo, role, status="Rejected", rejection_reason="duplicate")

    saved = result.application
    assert saved.status == Status.REJECTED
    assert saved.is_duplicate
    assert saved.extras["rejection_reason"] == "duplicate"
    assert saved.reviewed_at is not None
    assert repo.by_id(str(role.id)).is_duplicate  # survives the database round trip


@pytest.mark.asyncio
async def test_the_reason_alone_is_enough():
    repo = InMemoryApplicationRepository()
    role = make_application(status=Status.TO_VALIDATE)
    repo.add(role)

    saved = (await update(repo, role, rejection_reason="duplicate")).application

    assert saved.status == Status.REJECTED and saved.is_duplicate


@pytest.mark.asyncio
async def test_moving_the_role_to_any_other_status_drops_the_reason():
    repo = InMemoryApplicationRepository()
    role = make_application()
    repo.add(role)
    await update(repo, role, status="Rejected", rejection_reason="duplicate")

    saved = (await update(repo, role, status="To validate")).application

    assert saved.status == Status.TO_VALIDATE
    assert not saved.is_duplicate
    assert "rejection_reason" not in saved.extras


@pytest.mark.asyncio
async def test_a_plain_reject_after_a_duplicate_is_an_ordinary_rejection():
    repo = InMemoryApplicationRepository()
    role = make_application()
    repo.add(role)
    await update(repo, role, status="Rejected", rejection_reason="duplicate")

    saved = (await update(repo, role, status="Rejected")).application

    assert saved.status == Status.REJECTED
    assert not saved.is_duplicate


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [{"rejection_reason": "boring"}, {"status": "Approved", "rejection_reason": "duplicate"}],
)
async def test_an_unknown_reason_or_a_duplicate_that_is_not_a_rejection_is_refused(fields):
    repo = InMemoryApplicationRepository()
    role = make_application()
    repo.add(role)

    with pytest.raises(InvalidValueError):
        await update(repo, role, **fields)

    assert repo.by_id(str(role.id)).status == Status.TO_VALIDATE  # nothing changed


def rejected(duplicate, **overrides):
    extras = {"rejection_reason": "duplicate"} if duplicate else {}
    return make_application(status=Status.REJECTED, score=90, discovery_queries=["line a"], tags=["big_corporate"], extras=extras, **overrides)


def test_the_feedback_signals_do_not_read_a_duplicate_as_taste():
    taste, copy = rejected(False), rejected(True)

    performance = query_performance([taste, copy])["line a"]
    assert (performance["rejected"], performance["duplicate"], performance["surfaced"]) == (1, 1, 2)
    assert [r["id"] for r in disagreements([taste, copy])["rejected_high_score"]] == [str(taste.id)]
    summary = summarize([taste, copy])
    assert summary["tags_on_rejected"] == {"big_corporate": 1}
    assert summary["duplicates"] == 1


@pytest.mark.asyncio
async def test_a_repost_of_a_duplicate_does_not_bring_it_back():
    repo = InMemoryApplicationRepository()
    base = {"id": "4001", "title": "Applied AI Engineer", "company": "Acme AI", "score": 82, "jd_url": "https://x/4001", "run_date": "2026-09-17"}
    ingest = IngestBatchHandler(repository=repo).execute
    await ingest(IngestBatchCommand(roles=[base]))
    await ingest(IngestBatchCommand(roles=[{**base, "id": "9001", "title": "Other", "company": "Other Co", "run_date": "2026-10-10"}]))
    (acme,) = [a for a in await repo.list() if a.company == "Acme AI"]
    await update(repo, acme, status="Rejected", rejection_reason="duplicate")

    result = await ingest(IngestBatchCommand(roles=[{**base, "id": "5002", "jd_url": "https://x/5002", "run_date": "2026-11-16"}]))

    (after,) = [a for a in await repo.list() if a.company == "Acme AI"]
    assert after.is_duplicate and after.status == Status.REJECTED
    assert result.returned[0]["status_reset"] is False
