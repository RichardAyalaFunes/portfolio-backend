"""SupabaseKnowledgeRepository against a mock HTTP transport: pins the requests it sends (table,
columns, filters, conflict target, body) and how it reads the replies, which the in-memory fake
cannot catch."""

import json

import pytest

from backend.domain.knowledge.page import KnowledgePage
from backend.infrastructure.adapters.driven.supabase.knowledge_repository import (
    SUMMARY_COLUMNS,
    SupabaseKnowledgeRepository,
)
from tests.infrastructure.test_supabase_adapters import Recorder, postgrest
from tests.support.knowledge_builders import make_document

ROW = {
    "slug": "reference/backend/idempotency",
    "space": "reference",
    "kind": "concept",
    "title": "Idempotency",
    "group_label": "Backend",
    "group_order": 1,
    "sort_order": 3,
    "domain": "backend",
    "summary": "Doing it twice is safe.",
    "read_minutes": 3,
    "tags": ["reliability"],
    "aliases": ["idempotent"],
    "source_updated": "2026-09-30",
}


@pytest.mark.asyncio
async def test_upsert_sends_every_row_with_the_database_column_names_on_the_slug_conflict():
    recorder = Recorder([])
    page = KnowledgePage.from_document(make_document(links=["reference/backend/dead-letter-queue"]))

    await SupabaseKnowledgeRepository(postgrest(recorder)).upsert([page])

    request = recorder.only
    body = json.loads(request.content)
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/knowledge_pages"
    assert request.url.params["on_conflict"] == "slug"
    assert "merge-duplicates" in request.headers["prefer"]
    assert len(body) == 1
    row = body[0]
    assert row["slug"] == "reference/backend/idempotency"
    assert row["group_label"] == "Backend"
    assert row["sort_order"] == 1
    assert row["links"] == ["reference/backend/dead-letter-queue"]
    assert row["tags"] == ["reliability", "retries"]
    assert row["body"]["blocks"][0]["t"] == "callout"
    assert "Retries happen" in row["search_text"]
    assert "group" not in row and "order" not in row


@pytest.mark.asyncio
async def test_upsert_with_no_pages_sends_nothing():
    recorder = Recorder([])

    await SupabaseKnowledgeRepository(postgrest(recorder)).upsert([])

    assert recorder.requests == []


@pytest.mark.asyncio
async def test_list_summaries_selects_the_light_columns_in_library_order_and_maps_names_back():
    recorder = Recorder([ROW])

    rows = await SupabaseKnowledgeRepository(postgrest(recorder)).list_summaries()

    request = recorder.only
    assert request.url.params["select"] == SUMMARY_COLUMNS
    assert "body" not in SUMMARY_COLUMNS and "search_text" not in SUMMARY_COLUMNS
    assert request.url.params["order"] == "space.asc,group_order.asc,group_label.asc,sort_order.asc,title.asc"
    assert rows == [
        {
            "slug": "reference/backend/idempotency",
            "space": "reference",
            "kind": "concept",
            "title": "Idempotency",
            "group": "Backend",
            "group_order": 1,
            "order": 3,
            "domain": "backend",
            "summary": "Doing it twice is safe.",
            "read_minutes": 3,
            "tags": ["reliability"],
            "aliases": ["idempotent"],
            "source_updated": "2026-09-30",
        }
    ]


@pytest.mark.asyncio
async def test_get_reads_one_slug_with_its_body_and_links():
    detail = {**ROW, "links": ["reference/backend/dead-letter-queue"], "body": {"blocks": []}, "source_path": "x.md", "content_hash": "h", "published_at": "2026-10-01T10:00:00+00:00"}
    recorder = Recorder([detail])

    page = await SupabaseKnowledgeRepository(postgrest(recorder)).get("reference/backend/idempotency")

    request = recorder.only
    assert request.url.params["slug"] == "eq.reference/backend/idempotency"
    assert request.url.params["limit"] == "1"
    assert "body" in request.url.params["select"] and "links" in request.url.params["select"]
    assert page["body"] == {"blocks": []}
    assert page["links"] == ["reference/backend/dead-letter-queue"]
    assert page["group"] == "Backend"


@pytest.mark.asyncio
async def test_get_returns_none_for_an_unknown_slug():
    assert await SupabaseKnowledgeRepository(postgrest(Recorder([]))).get("reference/x/y") is None


@pytest.mark.asyncio
async def test_backlinks_filter_on_array_containment_and_never_return_the_page_itself():
    recorder = Recorder([ROW, {**ROW, "slug": "reference/backend/other", "title": "Other"}])

    rows = await SupabaseKnowledgeRepository(postgrest(recorder)).backlinks("reference/backend/idempotency")

    request = recorder.only
    assert request.url.params["links"] == "cs.{reference/backend/idempotency}"
    assert [r["slug"] for r in rows] == ["reference/backend/other"]


@pytest.mark.asyncio
async def test_delete_filters_the_slugs_with_in():
    recorder = Recorder([])

    await SupabaseKnowledgeRepository(postgrest(recorder)).delete(["reference/a/b", "learn/c/d"])

    request = recorder.only
    assert request.method == "DELETE"
    assert request.url.params["slug"] == "in.(reference/a/b,learn/c/d)"


@pytest.mark.asyncio
async def test_match_sends_one_word_start_regex_filter_per_term_and_escapes_the_term():
    recorder = Recorder([ROW])

    rows = await SupabaseKnowledgeRepository(postgrest(recorder)).match(["race", "c++"])

    request = recorder.only
    assert request.url.params.get_list("search_text") == ["imatch.\\mrace", "imatch.\\mc\\+\\+"]
    assert "search_text" not in request.url.params["select"]
    assert [r["slug"] for r in rows] == ["reference/backend/idempotency"]


@pytest.mark.asyncio
async def test_search_texts_maps_slug_to_text_and_skips_the_call_for_an_empty_list():
    recorder = Recorder([{"slug": "reference/backend/idempotency", "search_text": "Retries happen"}])
    repository = SupabaseKnowledgeRepository(postgrest(recorder))

    assert await repository.search_texts([]) == {}
    assert recorder.requests == []

    texts = await repository.search_texts(["reference/backend/idempotency"])

    assert texts == {"reference/backend/idempotency": "Retries happen"}
    assert recorder.only.url.params["select"] == "slug,search_text"
