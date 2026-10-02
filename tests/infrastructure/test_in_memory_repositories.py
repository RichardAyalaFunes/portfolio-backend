"""The in-memory fakes in tests/support/in_memory.py stand in for Supabase in the route
tests and in scripts/dev_fake_server.py, so they need to behave like it where the
dashboard relies on it: list filters, the default sort, timestamps, the unique key."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.domain.applications.value_objects import Stage, Status
from tests.support.builders import make_application
from tests.support.in_memory import (
    InMemoryApplicationRepository,
    InMemoryLoginAttemptRepository,
    InMemoryRulesRepository,
    InMemoryRunRepository,
)

TODAY = date(2026, 10, 1)


def build_repo():
    repo = InMemoryApplicationRepository()
    repo.add(
        make_application(
            title="Applied AI Engineer", company="Acme Robotics", group="ai_engineer", source="linkedin",
            status=Status.APPROVED, application_stage=Stage.APPLIED, live_state="LISTED",
            run_date=TODAY, posted_date=TODAY - timedelta(days=1), score=90,
        ),
        make_application(
            title="Founding Engineer", company="Brightwave", group="founding_engineer", source="yc",
            status=Status.TO_VALIDATE, live_state="CLOSED",
            run_date=TODAY - timedelta(days=7), posted_date=TODAY - timedelta(days=5), score=70,
        ),
        make_application(
            title="Forward Deployed Engineer", company="Cobalt Harbor", group="forward_deployed_engineer",
            source="linkedin", status=Status.TO_VALIDATE, posted_date=None, score=80,
        ),
        make_application(
            title="Archived Role", company="Gone Co", posted_date=TODAY - timedelta(days=3),
            archived_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        ),
    )
    return repo


async def titles(repo, **filters):
    return [a.title for a in await repo.list(**filters)]


@pytest.mark.asyncio
async def test_list_hides_archived_roles_unless_asked():
    repo = build_repo()

    assert "Archived Role" not in await titles(repo)
    assert "Archived Role" in await titles(repo, include_archived=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"status": "Approved"}, ["Applied AI Engineer"]),
        ({"stage": "Applied"}, ["Applied AI Engineer"]),
        ({"group": "founding_engineer"}, ["Founding Engineer"]),
        ({"source": "yc"}, ["Founding Engineer"]),
        ({"live_state": "CLOSED"}, ["Founding Engineer"]),
        ({"run_date": "2026-10-01"}, ["Applied AI Engineer"]),
        ({"query": "robotics"}, ["Applied AI Engineer"]),
        ({"query": "FOUNDING"}, ["Founding Engineer"]),
        ({"status": "To validate", "source": "linkedin"}, ["Forward Deployed Engineer"]),
        ({"status": "Rejected"}, []),
    ],
)
async def test_list_filters_like_the_database_does(filters, expected):
    assert await titles(build_repo(), **filters) == expected


@pytest.mark.asyncio
async def test_default_sort_is_posted_date_descending_with_null_dates_first_like_postgres():
    assert await titles(build_repo()) == ["Forward Deployed Engineer", "Applied AI Engineer", "Founding Engineer"]


@pytest.mark.asyncio
async def test_explicit_sort_and_direction():
    repo = build_repo()

    assert await titles(repo, sort="score.asc") == ["Founding Engineer", "Forward Deployed Engineer", "Applied AI Engineer"]
    assert await titles(repo, sort="score.desc") == ["Applied AI Engineer", "Forward Deployed Engineer", "Founding Engineer"]
    assert await titles(repo, sort="posted_date.asc") == [
        "Founding Engineer", "Applied AI Engineer", "Forward Deployed Engineer",
    ]
    with pytest.raises(ValueError, match="unknown sort column"):
        await repo.list(sort="nope.asc")


@pytest.mark.asyncio
async def test_reads_return_copies_so_mutating_one_never_changes_the_store():
    repo = InMemoryApplicationRepository()
    application = make_application(tags=["salary_unknown"])
    repo.add(application)

    first = await repo.get(application.id)
    first.tags.append("changed")
    first.title = "changed"

    again = await repo.get(application.id)
    assert again.tags == ["salary_unknown"]
    assert again.title == application.title


@pytest.mark.asyncio
async def test_create_and_update_stamp_the_timestamps_the_database_would():
    repo = InMemoryApplicationRepository()

    created = await repo.create(make_application())
    assert created.created_at is not None
    assert created.updated_at == created.created_at

    created.notes = "edited"
    updated = await repo.update(created)
    assert updated.notes == "edited"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at


@pytest.mark.asyncio
async def test_create_refuses_a_duplicate_identity_key_and_update_needs_an_existing_row():
    repo = InMemoryApplicationRepository()
    await repo.create(make_application(identity_key="acme::engineer"))

    with pytest.raises(ValueError, match="duplicate identity_key"):
        await repo.create(make_application(identity_key="acme::engineer"))
    with pytest.raises(LookupError):
        await repo.update(make_application())
    assert (await repo.get_by_identity_key("acme::engineer")) is not None
    assert (await repo.get_by_identity_key("missing")) is None


@pytest.mark.asyncio
async def test_a_stored_role_goes_through_the_mappers_so_iso_strings_become_dates():
    repo = InMemoryApplicationRepository()
    application = make_application(posted_date="2026-09-17", run_date="2026-09-18")  # strings, as ingest passes them

    created = await repo.create(application)

    assert created.posted_date == date(2026, 9, 17)
    assert created.run_date == date(2026, 9, 18)


@pytest.mark.asyncio
async def test_run_repository_lists_newest_first_and_upserts_by_run_date():
    repo = InMemoryRunRepository([{"run_date": "2026-09-01"}, {"run_date": "2026-09-20", "label": "old"}])

    await repo.upsert({"run_date": "2026-09-20", "label": "new"})
    await repo.upsert({"run_date": "2026-09-10"})

    runs = await repo.list_all()
    assert [r["run_date"] for r in runs] == ["2026-09-20", "2026-09-10", "2026-09-01"]
    assert runs[0]["label"] == "new"


@pytest.mark.asyncio
async def test_rules_repository_is_a_singleton_that_publish_replaces():
    repo = InMemoryRulesRepository()
    assert await repo.get() is None

    first = await repo.publish({"schema_version": 1, "lanes": [], "n": 1})
    second = await repo.publish({"schema_version": 1, "lanes": [], "n": 2})

    stored = await repo.get()
    assert stored["content"]["n"] == 2
    assert stored["published_at"] == second
    assert datetime.fromisoformat(first) <= datetime.fromisoformat(second)


@pytest.mark.asyncio
async def test_login_attempts_count_by_device_or_ip_and_ignore_old_or_successful_ones():
    repo = InMemoryLoginAttemptRepository()
    await repo.record(ip="1.1.1.1", device_id="dev-a", success=False)
    await repo.record(ip="2.2.2.2", device_id="dev-b", success=False)
    await repo.record(ip="1.1.1.1", device_id="dev-a", success=True)
    since = datetime.now(tz=timezone.utc) - timedelta(hours=1)

    assert await repo.count_recent_failures(ip="1.1.1.1", device_id="other", since=since) == 1
    assert await repo.count_recent_failures(ip="9.9.9.9", device_id="dev-b", since=since) == 1
    assert await repo.count_recent_failures(ip=None, device_id="dev-a", since=since) == 1
    assert await repo.count_recent_failures(ip=None, device_id="nobody", since=since) == 0
    assert await repo.count_recent_failures(
        ip="1.1.1.1", device_id="dev-a", since=datetime.now(tz=timezone.utc) + timedelta(hours=1)
    ) == 0
