"""ingest --replace must correct the verdict of an existing row (score, band, drop
stage/reason, why_not), not only its status. Fields the caller omits stay as stored."""

import pytest

from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from tests.support.in_memory import InMemoryApplicationRepository


def role(**overrides):
    base = {
        "id": "4001", "title": "Full Stack Engineer", "company": "Acme AI", "group": "backend",
        "score": 72, "status": "To validate", "why_not": "old reason", "considerations": "keep me",
        "jd_url": "https://www.linkedin.com/jobs/view/4001", "source": "linkedin", "run_date": "2026-11-24",
    }
    base.update(overrides)
    return base


async def ingest(repo, *roles, replace=False):
    return await IngestBatchHandler(repository=repo).execute(IngestBatchCommand(roles=list(roles), replace=replace))


async def only(repo):
    rows = [a for a in await repo.list(include_archived=False) if a.company == "Acme AI"]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_replace_corrects_score_and_drop_fields():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())
    fix = role(status="Dropped", drop_stage="scored", drop_reason="below_bar", why_not="new reason")
    fix.pop("considerations")
    await ingest(repo, fix, replace=True)
    row = await only(repo)
    assert row.status.value == "Dropped"
    assert (row.drop_stage, row.drop_reason, row.why_not) == ("scored", "below_bar", "new reason")
    assert row.score == 72 and row.band == "below"
    assert row.considerations == "keep me"  # omitted field untouched


@pytest.mark.asyncio
async def test_replace_with_null_score_clears_it_and_rescore_moves_band():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())
    await ingest(repo, role(status="Dropped", score=None, drop_stage="read", drop_reason="eligibility_geo"), replace=True)
    row = await only(repo)
    assert row.score is None and (row.drop_stage, row.drop_reason) == ("read", "eligibility_geo")
    await ingest(repo, role(status="Flagged", score=76, drop_stage=None, drop_reason=None), replace=True)
    row = await only(repo)
    assert row.score == 76 and row.band == "good" and row.drop_reason is None


@pytest.mark.asyncio
async def test_merge_mode_still_leaves_verdict_alone():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())
    await ingest(repo, role(score=40, why_not="should not land"))
    row = await only(repo)
    assert row.score == 72 and row.why_not == "old reason"
