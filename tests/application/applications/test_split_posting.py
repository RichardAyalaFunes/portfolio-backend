"""Splitting one wrongly merged posting off a role into a row of its own."""

import pytest

from backend.application.applications.split_posting.command import SplitPostingCommand
from backend.application.applications.split_posting.handler import SplitPostingHandler
from backend.domain.applications.value_objects import Stage, Status
from backend.domain.shared.errors import InvalidValueError, NotFoundError
from tests.support.builders import make_application
from tests.support.in_memory import InMemoryApplicationRepository


def posting(posting_id, run_date="2026-10-01"):
    return {
        "id": posting_id,
        "url": f"https://example.com/jobs/{posting_id}",
        "source": "linkedin",
        "run_date": run_date,
        "posted_date": run_date,
        "live_state": None,
    }


def merged_role(**overrides):
    fields = {
        "company": "Acme AI",
        "title": "Applied AI Engineer",
        "status": Status.REJECTED,
        "application_stage": Stage.APPLIED,
        "notes": "my note",
        "postings": [posting("5002", "2026-11-16"), posting("4001", "2026-09-17")],
        "extras": {"returns": [{"kind": "reposted", "posting_id": "5002"}, {"kind": "reposted", "posting_id": "4001"}]},
    }
    fields.update(overrides)
    return make_application(**fields)


async def split(repo, application, posting_id):
    return await SplitPostingHandler(repository=repo).execute(
        SplitPostingCommand(application_id=str(application.id), posting_id=posting_id)
    )


@pytest.mark.asyncio
async def test_the_posting_becomes_its_own_role_in_the_review_queue():
    repo = InMemoryApplicationRepository()
    role = merged_role()
    repo.add(role)

    result = await split(repo, role, "5002")

    assert [p["id"] for p in result.original.postings] == ["4001"]
    created = result.created
    assert [p["id"] for p in created.postings] == ["5002"]
    assert created.status == Status.TO_VALIDATE
    assert created.application_stage == Stage.NOT_APPLIED
    assert created.notes == ""
    assert (created.company, created.title) == ("Acme AI", "Applied AI Engineer")
    assert created.jd_url == "https://example.com/jobs/5002"
    assert created.extras["split_from"] == str(role.id)
    assert created.identity_key != role.identity_key


@pytest.mark.asyncio
async def test_what_richard_decided_stays_with_the_original():
    repo = InMemoryApplicationRepository()
    role = merged_role()
    repo.add(role)

    result = await split(repo, role, "5002")

    assert result.original.status == Status.REJECTED
    assert result.original.application_stage == Stage.APPLIED
    assert result.original.notes == "my note"


@pytest.mark.asyncio
async def test_the_comeback_record_of_that_posting_leaves_with_it():
    repo = InMemoryApplicationRepository()
    role = merged_role()
    repo.add(role)

    result = await split(repo, role, "5002")

    assert [e["posting_id"] for e in result.original.extras["returns"]] == ["4001"]


@pytest.mark.asyncio
async def test_the_only_posting_cannot_be_split():
    repo = InMemoryApplicationRepository()
    role = merged_role(postings=[posting("4001")], extras={})
    repo.add(role)

    with pytest.raises(InvalidValueError):
        await split(repo, role, "4001")


@pytest.mark.asyncio
async def test_an_unknown_posting_is_not_found():
    repo = InMemoryApplicationRepository()
    role = merged_role()
    repo.add(role)

    with pytest.raises(NotFoundError):
        await split(repo, role, "nope")
