"""The Supabase adapters against a mock HTTP transport: no network, no database. The
in-memory fakes cannot catch a typo in the real PostgREST calls, so these pin the
requests the new adapter and the mapper wiring actually send (path, filters, upsert
conflict target, body) and how they read the replies."""

import json
from datetime import datetime

import httpx
import pytest
from postgrest import AsyncPostgrestClient

from backend.domain.applications.skill_match import normalize_skill_match
from backend.infrastructure.adapters.driven.supabase.application_repository import (
    SupabaseJobApplicationRepository,
)
from backend.infrastructure.adapters.driven.supabase.mappers import entity_to_row
from backend.infrastructure.adapters.driven.supabase.search_rules_repository import (
    SupabaseSearchRulesRepository,
)
from tests.support.builders import make_application, skill_match_payload


class Recorder:
    """httpx mock-transport handler: records each request and replies with a canned body."""

    def __init__(self, body, status=200):
        self.requests: list[httpx.Request] = []
        self.body = body
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)

    @property
    def only(self) -> httpx.Request:
        assert len(self.requests) == 1
        return self.requests[0]


def postgrest(recorder: Recorder) -> AsyncPostgrestClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return AsyncPostgrestClient("https://example.invalid/rest/v1", http_client=http)


RULES = {"schema_version": 1, "lanes": [{"id": "ai_engineer", "label": "AI Engineer", "lines": []}]}


# -- SupabaseSearchRulesRepository -------------------------------------------------


@pytest.mark.asyncio
async def test_rules_get_reads_the_singleton_row_and_returns_content_and_published_at():
    recorder = Recorder([{"content": RULES, "published_at": "2026-10-01T12:00:00+00:00"}])

    stored = await SupabaseSearchRulesRepository(postgrest(recorder)).get()

    request = recorder.only
    assert request.method == "GET"
    assert request.url.path == "/rest/v1/job_search_rules"
    assert request.url.params["id"] == "eq.1"
    assert request.url.params["limit"] == "1"
    assert request.url.params["select"] == "content,published_at"
    assert stored == {"content": RULES, "published_at": "2026-10-01T12:00:00+00:00"}


@pytest.mark.asyncio
async def test_rules_get_returns_none_when_nothing_was_published():
    stored = await SupabaseSearchRulesRepository(postgrest(Recorder([]))).get()

    assert stored is None


@pytest.mark.asyncio
async def test_rules_publish_upserts_row_one_on_the_id_conflict_and_returns_the_timestamp_it_sent():
    recorder = Recorder([{"id": 1}])

    published_at = await SupabaseSearchRulesRepository(postgrest(recorder)).publish(RULES)

    request = recorder.only
    body = json.loads(request.content)
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/job_search_rules"
    assert request.url.params["on_conflict"] == "id"
    assert "merge-duplicates" in request.headers["prefer"]
    assert body == {"id": 1, "content": RULES, "published_at": published_at}
    assert datetime.fromisoformat(published_at).utcoffset().total_seconds() == 0  # timezone-aware UTC


# -- the application repository carries skill_match --------------------------------


@pytest.mark.asyncio
async def test_update_writes_the_skill_match_column():
    application = make_application()
    application.set_skill_match(normalize_skill_match(skill_match_payload()))
    recorder = Recorder([entity_to_row(application)])

    updated = await SupabaseJobApplicationRepository(postgrest(recorder)).update(application)

    request = recorder.only
    body = json.loads(request.content)
    assert request.method == "PATCH"
    assert request.url.params["id"] == f"eq.{application.id}"
    assert body["skill_match"] == application.skill_match
    assert "id" not in body and "created_at" not in body and "updated_at" not in body
    assert updated.skill_match == application.skill_match


@pytest.mark.asyncio
async def test_save_skill_match_patches_that_one_column_and_nothing_else():
    application = make_application(notes="written by Richard", group="ai_engineer")
    application.set_skill_match(normalize_skill_match(skill_match_payload()))
    recorder = Recorder([entity_to_row(application)])

    result = await SupabaseJobApplicationRepository(postgrest(recorder)).save_skill_match(application)

    request = recorder.only
    assert result is None
    assert request.method == "PATCH"
    assert request.url.path == "/rest/v1/job_applications"
    assert request.url.params["id"] == f"eq.{application.id}"
    # Only the skill table travels: no status, stage or note that could overwrite his edits.
    assert json.loads(request.content) == {"skill_match": application.skill_match}


@pytest.mark.asyncio
async def test_list_reads_the_skill_match_column_and_defaults_it_for_older_rows():
    analysed = make_application()
    analysed.set_skill_match(normalize_skill_match(skill_match_payload()))
    plain_row = entity_to_row(make_application())
    del plain_row["skill_match"]  # a row that predates migration 004
    recorder = Recorder([entity_to_row(analysed), plain_row])

    applications = await SupabaseJobApplicationRepository(postgrest(recorder)).list()

    assert recorder.only.url.params["archived_at"] == "is.null"
    assert recorder.only.url.params["order"] == "posted_date.desc"
    assert applications[0].skill_match == analysed.skill_match
    assert applications[1].skill_match == {}
