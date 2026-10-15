"""Publish, prune, index, page and search, against the in-memory repository."""

import pytest

from backend.application.knowledge.get_index.command import GetKnowledgeIndexCommand
from backend.application.knowledge.get_index.handler import GetKnowledgeIndexHandler
from backend.application.knowledge.get_page.command import GetKnowledgePageCommand
from backend.application.knowledge.get_page.handler import GetKnowledgePageHandler
from backend.application.knowledge.prune_pages.command import PruneKnowledgePagesCommand
from backend.application.knowledge.prune_pages.handler import PruneKnowledgePagesHandler
from backend.application.knowledge.publish_pages.command import PublishKnowledgePagesCommand
from backend.application.knowledge.publish_pages.handler import PublishKnowledgePagesHandler
from backend.application.knowledge.search.command import SearchKnowledgeCommand
from backend.application.knowledge.search.handler import SearchKnowledgeHandler, tokenize
from backend.domain.shared.errors import InvalidValueError, NotFoundError
from tests.support.in_memory import InMemoryKnowledgeRepository
from tests.support.knowledge_builders import make_document

IDEMPOTENCY = "reference/backend/idempotency"
DLQ = "reference/backend/dead-letter-queue"
LESSON = "learn/1-backend/1-4-queues-and-retries"


@pytest.fixture
def repository():
    return InMemoryKnowledgeRepository()


async def publish(repository, *documents):
    return await PublishKnowledgePagesHandler(repository).execute(PublishKnowledgePagesCommand(pages=list(documents)))


async def seeded(repository):
    await publish(
        repository,
        make_document(IDEMPOTENCY, links=[DLQ]),
        make_document(
            DLQ,
            title="Dead letter queue (DLQ)",
            aliases=["DLQ", "dead letter"],
            tags=["reliability", "queues"],
            links=[IDEMPOTENCY],
            search_text="Dead letter queue (DLQ)\nDLQ\ndead letter\nreliability\nqueues\nA message that keeps failing is moved aside so it stops blocking the queue.",
            order=2,
        ),
        make_document(
            LESSON,
            title="1.4 Queues and retries",
            kind="topic",
            group="Backend",
            group_order=1,
            order=1004,
            links=[IDEMPOTENCY, DLQ],
            aliases=[],
            tags=[],
            search_text="1.4 Queues and retries\nWorkers retry. Make every handler idempotent and send poison messages to the dead letter queue.",
        ),
    )


# -- publish ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_stores_pages_and_reports_how_many(repository):
    result = await publish(repository, make_document(IDEMPOTENCY), make_document(DLQ, title="DLQ"))

    assert result.upserted == 2
    assert repository.slugs() == [DLQ, IDEMPOTENCY]


@pytest.mark.asyncio
async def test_publish_is_an_upsert_by_slug(repository):
    await publish(repository, make_document(IDEMPOTENCY))
    await publish(repository, make_document(IDEMPOTENCY, title="Idempotency, revised"))

    assert repository.slugs() == [IDEMPOTENCY]
    assert repository.row(IDEMPOTENCY)["title"] == "Idempotency, revised"


@pytest.mark.asyncio
async def test_publish_rejects_the_whole_batch_when_one_page_is_invalid(repository):
    with pytest.raises(InvalidValueError, match="kind"):
        await publish(repository, make_document(IDEMPOTENCY), make_document(DLQ, kind="essay"))

    assert repository.slugs() == []


@pytest.mark.asyncio
async def test_publish_rejects_an_empty_batch_and_a_repeated_slug(repository):
    with pytest.raises(InvalidValueError, match="empty"):
        await publish(repository)
    with pytest.raises(InvalidValueError, match="twice"):
        await publish(repository, make_document(IDEMPOTENCY), make_document(IDEMPOTENCY))


# -- prune -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_removes_pages_that_are_not_kept(repository):
    await seeded(repository)

    result = await PruneKnowledgePagesHandler(repository).execute(PruneKnowledgePagesCommand(keep=[IDEMPOTENCY, DLQ]))

    assert result.removed == 1
    assert repository.slugs() == [DLQ, IDEMPOTENCY]


@pytest.mark.asyncio
async def test_prune_refuses_an_empty_keep_list_and_a_malformed_slug(repository):
    await seeded(repository)

    with pytest.raises(InvalidValueError, match="empty"):
        await PruneKnowledgePagesHandler(repository).execute(PruneKnowledgePagesCommand(keep=[]))
    with pytest.raises(InvalidValueError, match="slug"):
        await PruneKnowledgePagesHandler(repository).execute(PruneKnowledgePagesCommand(keep=["Bad Slug"]))
    assert len(repository.slugs()) == 3


@pytest.mark.asyncio
async def test_prune_refuses_to_remove_more_than_half_of_a_real_library(repository):
    documents = [make_document(f"reference/backend/note-{n}", title=f"Note {n}") for n in range(12)]
    await publish(repository, *documents)

    with pytest.raises(InvalidValueError, match="refusing"):
        await PruneKnowledgePagesHandler(repository).execute(
            PruneKnowledgePagesCommand(keep=["reference/backend/note-0", "reference/backend/note-1"])
        )
    assert len(repository.slugs()) == 12


# -- index and page ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_returns_summary_rows_in_library_order_without_bodies(repository):
    await seeded(repository)

    result = await GetKnowledgeIndexHandler(repository).execute(GetKnowledgeIndexCommand())

    assert [p["slug"] for p in result.pages] == [LESSON, IDEMPOTENCY, DLQ]  # learn before reference, then order
    assert "body" not in result.pages[0]
    assert "search_text" not in result.pages[0]
    assert result.pages[1]["tags"] == ["reliability", "retries"]


@pytest.mark.asyncio
async def test_page_returns_the_body_and_the_pages_that_link_to_it(repository):
    await seeded(repository)

    result = await GetKnowledgePageHandler(repository).execute(GetKnowledgePageCommand(slug=IDEMPOTENCY))

    assert result.page["title"] == "Idempotency"
    assert result.page["body"]["blocks"][0]["t"] == "callout"
    assert result.page["links"] == [DLQ]
    assert [b["slug"] for b in result.backlinks] == [LESSON, DLQ]
    assert "body" not in result.backlinks[0]


@pytest.mark.asyncio
async def test_page_raises_not_found_for_an_unknown_slug(repository):
    with pytest.raises(NotFoundError):
        await GetKnowledgePageHandler(repository).execute(GetKnowledgePageCommand(slug="reference/backend/missing"))


# -- search ------------------------------------------------------------------------


def test_tokenize_lowercases_drops_one_letter_noise_and_keeps_order():
    assert tokenize("  Race  condition, a C++ lock! race ") == ["race", "condition", "c++", "lock"]
    assert tokenize("a ? !") == []


@pytest.mark.asyncio
async def test_search_finds_a_word_start_and_not_the_middle_of_a_word(repository):
    await seeded(repository)
    handler = SearchKnowledgeHandler(repository)

    prefix = await handler.execute(SearchKnowledgeCommand(query="idemp"))
    assert {r["slug"] for r in prefix.results} == {IDEMPOTENCY, LESSON}

    middle = await handler.execute(SearchKnowledgeCommand(query="otent"))
    assert middle.results == []


@pytest.mark.asyncio
async def test_search_requires_every_term_and_ranks_a_title_hit_first(repository):
    await seeded(repository)
    handler = SearchKnowledgeHandler(repository)

    result = await handler.execute(SearchKnowledgeCommand(query="dead letter"))
    assert [r["slug"] for r in result.results][0] == DLQ
    assert LESSON in [r["slug"] for r in result.results]
    assert result.results[0]["matched_in"] == "title"

    none = await handler.execute(SearchKnowledgeCommand(query="dead blockchain"))
    assert none.total == 0


@pytest.mark.asyncio
async def test_search_returns_a_snippet_from_the_body_around_the_first_hit(repository):
    await seeded(repository)

    result = await SearchKnowledgeHandler(repository).execute(SearchKnowledgeCommand(query="poison"))

    assert [r["slug"] for r in result.results] == [LESSON]
    assert "poison messages" in result.results[0]["snippet"]
    assert result.results[0]["matched_in"] == "text"
    assert "aliases" not in result.results[0]


@pytest.mark.asyncio
async def test_search_with_only_noise_returns_nothing(repository):
    await seeded(repository)

    result = await SearchKnowledgeHandler(repository).execute(SearchKnowledgeCommand(query="?? !"))

    assert result.results == []
    assert result.terms == []
