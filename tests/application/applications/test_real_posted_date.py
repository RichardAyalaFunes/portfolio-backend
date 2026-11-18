"""A re-sent role carrying the platform's real listing date corrects an earlier estimate."""

from datetime import date

from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from tests.support.in_memory import InMemoryApplicationRepository


def role(**overrides):
    base = {
        "id": "4001", "title": "AI Engineer", "company": "Acme AI", "group": "ai_engineer",
        "score": 82, "jd_url": "https://www.linkedin.com/jobs/view/4001", "source": "linkedin",
        "run_date": "2026-11-17", "posted_relative": "within the last 2 days",
    }
    base.update(overrides)
    return base


async def ingest(repo, r):
    return await IngestBatchHandler(repository=repo).execute(IngestBatchCommand(roles=[r]))


async def row(repo):
    return (await repo.list(include_archived=False))[0]


async def test_real_date_replaces_the_estimate():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())
    estimated = await row(repo)
    assert estimated.posted_date == date(2026, 11, 15)
    assert estimated.posted_date_source == "derived_from_relative"

    await ingest(repo, role(posted_date="2026-11-17", posted_date_source="linkedin_listedAt"))
    fixed = await row(repo)
    assert fixed.posted_date == date(2026, 11, 17)
    assert fixed.posted_date_source == "linkedin_listedAt"
    assert fixed.postings[0]["posted_date"] == "2026-11-17"


async def test_an_estimate_never_overwrites_a_real_date():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role(posted_date="2026-11-17", posted_date_source="linkedin_listedAt"))
    await ingest(repo, role(run_date="2026-11-18", posted_relative="within the last 5 days"))
    kept = await row(repo)
    assert kept.posted_date == date(2026, 11, 17)
    assert kept.posted_date_source == "linkedin_listedAt"
