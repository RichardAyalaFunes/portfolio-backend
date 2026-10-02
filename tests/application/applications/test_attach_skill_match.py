"""AttachSkillMatch: role resolution (id, LinkedIn id from a URL, exact URL), per-item
validation that never sinks the batch, clearing, and the two invariants that matter
to the rest of the system: it is an agent write (reviewed_at untouched) and an
ingest repost must not wipe the table. In-memory fakes -- no network."""

from datetime import datetime, timezone

import pytest

from backend.application.applications.attach_skill_match.command import (
    AttachSkillMatchCommand,
    AttachSkillMatchItem,
)
from backend.application.applications.attach_skill_match.handler import AttachSkillMatchHandler
from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from backend.domain.applications.skill_match import normalize_skill_match
from backend.domain.applications.value_objects import Status
from tests.support.builders import make_application, skill_match_payload, skill_match_row
from tests.support.in_memory import InMemoryApplicationRepository

LINKEDIN_URL = "https://www.linkedin.com/jobs/view/4001"


def role(**overrides):
    base = {
        "id": "4001",
        "title": "Applied AI Engineer",
        "company": "Acme AI",
        "group": "ai_engineer",
        "score": 82,
        "jd_url": LINKEDIN_URL,
        "source": "linkedin",
        "run_date": "2026-09-17",
    }
    base.update(overrides)
    return base


async def ingest(repo, *roles):
    return await IngestBatchHandler(repository=repo).execute(IngestBatchCommand(roles=list(roles)))


async def attach(repo, *items):
    return await AttachSkillMatchHandler(repository=repo).execute(AttachSkillMatchCommand(items=list(items)))


def item(skill_match, **identifiers):
    return AttachSkillMatchItem(skill_match=skill_match, **identifiers)


def only_application(repo):
    (application,) = repo.all()
    return application


# -- matching ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matches_by_application_id_and_stores_the_normalised_table():
    repo = InMemoryApplicationRepository()
    target = make_application(status=Status.APPROVED, notes="keep me", group="ai_engineer")
    bystander = make_application()
    repo.add(target, bystander)

    result = await attach(repo, item(skill_match_payload(), application_id=str(target.id)))

    assert (result.matched, result.updated, result.unmatched, result.invalid) == (1, 1, [], [])
    stored = repo.by_id(str(target.id))
    assert stored.skill_match == normalize_skill_match(skill_match_payload())
    assert stored.skill_match["summary"]["to_surface"] == 1
    # Nothing else on the role moved, and the other role was not touched.
    assert (stored.status, stored.notes, stored.group) == (Status.APPROVED, "keep me", "ai_engineer")
    assert repo.by_id(str(bystander.id)).skill_match == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4001/?trackingId=abc",
        "https://www.linkedin.com/jobs/search/?currentJobId=4001&geoId=1",
        "https://es.linkedin.com/jobs/view/4001",
    ],
)
async def test_matches_by_the_linkedin_job_id_inside_a_url(url):
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())

    result = await attach(repo, item(skill_match_payload(), jd_url=url))

    assert (result.matched, result.updated, result.unmatched) == (1, 1, [])
    assert only_application(repo).skill_match["rows"]


@pytest.mark.asyncio
async def test_matches_by_exact_url_against_jd_url_and_posting_urls():
    repo = InMemoryApplicationRepository()
    target = make_application(
        jd_url="https://jobs.example.com/acme/ai-engineer",
        postings=[{"id": None, "url": "https://boards.example.com/acme/ai-engineer"}],
    )
    repo.add(target, make_application(jd_url="https://jobs.example.com/other/role"))

    by_jd_url = await attach(repo, item(skill_match_payload(), jd_url="https://jobs.example.com/acme/ai-engineer"))
    assert by_jd_url.updated == 1
    assert repo.by_id(str(target.id)).skill_match

    await attach(repo, item(None, application_id=str(target.id)))  # clear, then match by posting url
    assert repo.by_id(str(target.id)).skill_match == {}
    by_posting_url = await attach(
        repo, item(skill_match_payload(), jd_url="https://boards.example.com/acme/ai-engineer")
    )

    assert by_posting_url.updated == 1
    assert repo.by_id(str(target.id)).skill_match


@pytest.mark.asyncio
async def test_a_non_linkedin_url_must_match_exactly():
    repo = InMemoryApplicationRepository()
    repo.add(make_application(jd_url="https://jobs.example.com/acme/ai-engineer"))

    result = await attach(repo, item(skill_match_payload(), jd_url="https://jobs.example.com/acme/ai-engineer/"))

    assert (result.matched, result.updated) == (0, 0)
    assert result.unmatched == ["https://jobs.example.com/acme/ai-engineer/"]


@pytest.mark.asyncio
async def test_application_id_is_tried_first_and_the_url_is_the_fallback():
    repo = InMemoryApplicationRepository()
    by_id_target = make_application()
    by_url_target = make_application(jd_url="https://jobs.example.com/b")
    repo.add(by_id_target, by_url_target)

    # Both identifiers present and they disagree: the id wins.
    first = await attach(
        repo, item(skill_match_payload(), application_id=str(by_id_target.id), jd_url="https://jobs.example.com/b")
    )
    assert first.updated == 1
    assert repo.by_id(str(by_id_target.id)).skill_match
    assert repo.by_id(str(by_url_target.id)).skill_match == {}

    # An unknown id with a matching URL falls back to the URL.
    second = await attach(
        repo,
        item(skill_match_payload(), application_id="00000000-0000-0000-0000-000000000000", jd_url="https://jobs.example.com/b"),
    )
    assert (second.matched, second.updated, second.unmatched) == (1, 1, [])
    assert repo.by_id(str(by_url_target.id)).skill_match


@pytest.mark.asyncio
async def test_application_id_ignores_case_and_surrounding_whitespace():
    repo = InMemoryApplicationRepository()
    target = make_application()
    repo.add(target)

    result = await attach(repo, item(skill_match_payload(), application_id=f"  {str(target.id).upper()} "))

    assert (result.matched, result.updated) == (1, 1)


@pytest.mark.asyncio
async def test_unmatched_items_are_reported_by_their_identifier_and_nothing_is_written():
    repo = InMemoryApplicationRepository()
    target = make_application()
    repo.add(target)
    before = repo.by_id(str(target.id))

    result = await attach(
        repo,
        item(skill_match_payload(), application_id="00000000-0000-0000-0000-000000000000"),
        item(skill_match_payload(), jd_url="https://www.linkedin.com/jobs/view/999999"),
        item(skill_match_payload()),
    )

    assert (result.matched, result.updated, result.invalid) == (0, 0, [])
    assert result.unmatched == [
        "00000000-0000-0000-0000-000000000000",
        "https://www.linkedin.com/jobs/view/999999",
        "(no identifier)",
    ]
    assert repo.by_id(str(target.id)) == before
    assert repo.by_id(str(target.id)).skill_match == {}


@pytest.mark.asyncio
async def test_archived_roles_are_not_matched():
    repo = InMemoryApplicationRepository()
    gone = make_application(archived_at=datetime.now(tz=timezone.utc))
    repo.add(gone)

    result = await attach(repo, item(skill_match_payload(), application_id=str(gone.id)))

    assert (result.matched, result.updated, result.unmatched) == (0, 0, [str(gone.id)])


# -- validation never sinks the batch ---------------------------------------------


@pytest.mark.asyncio
async def test_an_invalid_payload_is_reported_while_the_rest_of_the_batch_still_applies():
    repo = InMemoryApplicationRepository()
    first, broken, third = make_application(), make_application(), make_application()
    kept = normalize_skill_match(skill_match_payload(verdict="previous table"))
    broken.set_skill_match(kept)
    repo.add(first, broken, third)

    bad_payload = skill_match_payload(rows=[skill_match_row(match="excellent")])
    result = await attach(
        repo,
        item(skill_match_payload(), application_id=str(first.id)),
        item(bad_payload, application_id=str(broken.id)),
        item(skill_match_payload(verdict="third"), application_id=str(third.id)),
    )

    assert (result.matched, result.updated, result.unmatched) == (3, 2, [])
    assert len(result.invalid) == 1
    assert result.invalid[0].startswith(f"{broken.id}: rows[0].match.level must be one of strong, partial, gap")
    assert repo.by_id(str(first.id)).skill_match["verdict"].startswith("Strong technical fit")
    assert repo.by_id(str(third.id)).skill_match["verdict"] == "third"
    assert repo.by_id(str(broken.id)).skill_match == kept  # a rejected payload leaves the old table alone


@pytest.mark.asyncio
async def test_invalid_items_are_identified_by_url_when_that_is_all_the_agent_sent():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())

    result = await attach(repo, item({"rows": []}, jd_url=LINKEDIN_URL))

    assert (result.matched, result.updated, result.unmatched) == (1, 0, [])
    assert result.invalid == [f"{LINKEDIN_URL}: rows is required: a list of 1 to 40 requirement rows"]
    assert only_application(repo).skill_match == {}


@pytest.mark.asyncio
async def test_matched_counts_every_resolved_item_so_matched_is_updated_plus_invalid():
    repo = InMemoryApplicationRepository()
    one, two, three = make_application(), make_application(), make_application()
    repo.add(one, two, three)

    result = await attach(
        repo,
        item(skill_match_payload(), application_id=str(one.id)),
        item("not an object", application_id=str(two.id)),
        item(skill_match_payload(), application_id="nope"),
    )

    assert result.matched == result.updated + len(result.invalid) == 2
    assert result.unmatched == ["nope"]


# -- clearing ---------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("clear", [None, {}], ids=["null", "empty-object"])
async def test_none_or_an_empty_object_clears_the_table(clear):
    repo = InMemoryApplicationRepository()
    target = make_application()
    target.set_skill_match(normalize_skill_match(skill_match_payload()))
    repo.add(target)

    result = await attach(repo, item(clear, application_id=str(target.id)))

    assert (result.matched, result.updated, result.invalid) == (1, 1, [])
    assert repo.by_id(str(target.id)).skill_match == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("not_an_object", [[], "", 0, ["rows"]], ids=["empty-list", "empty-string", "zero", "list"])
async def test_a_falsy_value_that_is_not_an_object_is_invalid_not_a_clear(not_an_object):
    repo = InMemoryApplicationRepository()
    target = make_application()
    kept = normalize_skill_match(skill_match_payload())
    target.set_skill_match(kept)
    repo.add(target)

    result = await attach(repo, item(not_an_object, application_id=str(target.id)))

    assert (result.matched, result.updated) == (1, 0)
    assert result.invalid == [f"{target.id}: skill_match must be an object"]
    assert repo.by_id(str(target.id)).skill_match == kept


@pytest.mark.asyncio
async def test_a_second_write_replaces_the_first_wholesale():
    repo = InMemoryApplicationRepository()
    target = make_application()
    repo.add(target)

    await attach(repo, item(skill_match_payload(verdict="first"), application_id=str(target.id)))
    await attach(
        repo,
        item(skill_match_payload(verdict="second", rows=[skill_match_row("Only row")]), application_id=str(target.id)),
    )

    stored = repo.by_id(str(target.id)).skill_match
    assert stored["verdict"] == "second"
    assert [r["requirement"] for r in stored["rows"]] == ["Only row"]
    assert stored["summary"]["requirements"] == 1


# -- invariants with the rest of the system ---------------------------------------


@pytest.mark.asyncio
async def test_attaching_is_an_agent_write_and_never_marks_the_role_reviewed():
    repo = InMemoryApplicationRepository()
    unreviewed = make_application()
    reviewed_at = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    reviewed = make_application(reviewed_at=reviewed_at)
    repo.add(unreviewed, reviewed)

    await attach(
        repo,
        item(skill_match_payload(), application_id=str(unreviewed.id)),
        item(skill_match_payload(), application_id=str(reviewed.id)),
        item(None, application_id=str(reviewed.id)),
    )

    assert repo.by_id(str(unreviewed.id)).reviewed_at is None
    assert repo.by_id(str(reviewed.id)).reviewed_at == reviewed_at


@pytest.mark.asyncio
async def test_a_later_ingest_repost_of_the_same_role_keeps_the_skill_match():
    repo = InMemoryApplicationRepository()
    await ingest(repo, role())
    row_id = str(only_application(repo).id)
    await attach(repo, item(skill_match_payload(), application_id=row_id))
    attached = repo.by_id(row_id).skill_match
    assert attached["rows"]

    # Same company and title under a new posting id: IngestBatch folds it into the row.
    result = await ingest(repo, role(id="4002", jd_url="https://www.linkedin.com/jobs/view/4002"))

    assert (result.added, result.updated, result.reposts) == (0, 1, 1)
    folded = only_application(repo)
    assert len(folded.postings) == 2
    assert folded.skill_match == attached
    assert folded.reviewed_at is None
