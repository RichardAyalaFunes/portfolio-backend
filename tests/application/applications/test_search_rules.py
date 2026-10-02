"""Published search rules: PublishRules validates only what the dashboard cannot
render without, GetRules returns the stored document plus per-line and per-lane
stats computed from the roles at read time. In-memory fakes -- no network."""

import json
from datetime import datetime, timezone

import pytest

from backend.application.applications.get_feedback.handler import query_performance
from backend.application.applications.get_rules.command import GetRulesCommand
from backend.application.applications.get_rules.handler import GetRulesHandler, lane_stats, line_stats
from backend.application.applications.publish_rules.command import PublishRulesCommand
from backend.application.applications.publish_rules.handler import MAX_CONTENT_BYTES, PublishRulesHandler
from backend.domain.applications.value_objects import Stage, Status
from backend.domain.shared.errors import InvalidValueError
from tests.support.builders import make_application
from tests.support.in_memory import InMemoryApplicationRepository, InMemoryRulesRepository

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def lane(**overrides):
    base = {"id": "ai_engineer", "label": "AI Engineer", "lines": [{"line": '"ai engineer" @peru'}]}
    base.update(overrides)
    return base


def rules(**overrides):
    base = {"schema_version": 1, "lanes": [lane()]}
    base.update(overrides)
    return base


def publisher(repo=None):
    repo = repo or InMemoryRulesRepository()
    return PublishRulesHandler(repository=repo), repo


def getter(rules_repo=None, application_repo=None):
    rules_repo = rules_repo or InMemoryRulesRepository()
    application_repo = application_repo or InMemoryApplicationRepository()
    return GetRulesHandler(rules_repository=rules_repo, application_repository=application_repo)


# -- publish: validation ----------------------------------------------------------

SERIALISED_OVERHEAD = len(json.dumps(rules(blob=""), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

INVALID_RULES = [
    pytest.param(None, "rules must be a JSON object", id="none"),
    pytest.param([rules()], "rules must be a JSON object", id="list"),
    pytest.param("text", "rules must be a JSON object", id="string"),
    pytest.param({"lanes": [lane()]}, "schema_version must be an integer", id="schema-version-missing"),
    pytest.param(rules(schema_version="1"), "schema_version must be an integer", id="schema-version-string"),
    pytest.param(rules(schema_version=1.0), "schema_version must be an integer", id="schema-version-float"),
    pytest.param(rules(schema_version=True), "schema_version must be an integer", id="schema-version-bool"),
    pytest.param(rules(schema_version=None), "schema_version must be an integer", id="schema-version-null"),
    pytest.param({"schema_version": 1}, "lanes must be a non-empty list", id="lanes-missing"),
    pytest.param(rules(lanes=None), "lanes must be a non-empty list", id="lanes-null"),
    pytest.param(rules(lanes=[]), "lanes must be a non-empty list", id="lanes-empty"),
    pytest.param(rules(lanes={"id": "x"}), "lanes must be a non-empty list", id="lanes-object"),
    pytest.param(rules(lanes=["ai_engineer"]), "lanes[0] must be an object", id="lane-not-an-object"),
    pytest.param(rules(lanes=[lane(id="")]), "lanes[0].id must be a non-empty string", id="lane-id-empty"),
    pytest.param(rules(lanes=[lane(id="   ")]), "lanes[0].id must be a non-empty string", id="lane-id-blank"),
    pytest.param(rules(lanes=[lane(id=7)]), "lanes[0].id must be a non-empty string", id="lane-id-number"),
    pytest.param(rules(lanes=[lane(label="")]), "lanes[0].label must be a non-empty string", id="lane-label-empty"),
    pytest.param(rules(lanes=[lane(label=None)]), "lanes[0].label must be a non-empty string", id="lane-label-null"),
    pytest.param(rules(lanes=[lane(lines="x")]), "lanes[0].lines must be a list", id="lines-string"),
    pytest.param(rules(lanes=[lane(lines={})]), "lanes[0].lines must be a list", id="lines-object"),
    pytest.param(
        rules(lanes=[lane(), {k: v for k, v in lane(id="founding").items() if k != "lines"}]),
        "lanes[1].lines must be a list",
        id="second-lane-has-no-lines",
    ),
    pytest.param(
        rules(blob="x" * (MAX_CONTENT_BYTES - SERIALISED_OVERHEAD + 1)),
        f"rules are {MAX_CONTENT_BYTES + 1} bytes serialised, the maximum is {MAX_CONTENT_BYTES}",
        id="one-byte-too-big",
    ),
    pytest.param(
        rules(blob="\u00e9" * (MAX_CONTENT_BYTES // 2)),
        "bytes serialised, the maximum is 400000",
        id="size-is-bytes-not-characters",
    ),
    pytest.param(rules(blob=float("nan")), "rules must be plain JSON", id="nan"),
    pytest.param(rules(blob=object()), "rules must be plain JSON", id="not-serialisable"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "message"), INVALID_RULES)
async def test_publish_rejects_invalid_rules_and_stores_nothing(content, message):
    handler, repo = publisher()

    with pytest.raises(InvalidValueError) as caught:
        await handler.execute(PublishRulesCommand(content=content))

    assert message in str(caught.value)
    assert await repo.get() is None


@pytest.mark.asyncio
async def test_publish_rejects_a_circular_structure():
    handler, repo = publisher()
    content = rules()
    content["self"] = content

    with pytest.raises(InvalidValueError, match="plain JSON"):
        await handler.execute(PublishRulesCommand(content=content))
    assert await repo.get() is None


@pytest.mark.asyncio
async def test_publish_accepts_a_document_exactly_at_the_size_limit():
    handler, repo = publisher()
    content = rules(blob="x" * (MAX_CONTENT_BYTES - SERIALISED_OVERHEAD))
    assert len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) == MAX_CONTENT_BYTES

    await handler.execute(PublishRulesCommand(content=content))

    assert (await repo.get())["content"] == content


# -- publish: success -------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_counts_lanes_and_lines_and_keeps_the_document_as_sent():
    handler, repo = publisher()
    content = rules(
        config_updated_at="2026-09-17",
        thresholds={"pass_bar": 75},
        gates=[{"id": "eligibility"}],
        lanes=[
            lane(lines=[{"line": "a"}, {"line": "b"}], rubric=[{"dimension": "stack", "weight": 100}]),
            lane(id="founding_engineer", label="Founding Engineer", lines=[{"line": "c"}, "free text", 3, None]),
        ],
    )

    result = await handler.execute(PublishRulesCommand(content=content))

    assert (result.lanes, result.lines) == (2, 6)
    assert datetime.fromisoformat(result.published_at)
    stored = await repo.get()
    assert stored["content"] == content  # opaque: extra keys and odd line entries survive untouched
    assert stored["published_at"] == result.published_at


@pytest.mark.asyncio
async def test_publish_allows_a_lane_with_no_lines_yet():
    handler, _ = publisher()

    result = await handler.execute(PublishRulesCommand(content=rules(lanes=[lane(lines=[])])))

    assert (result.lanes, result.lines) == (1, 0)


@pytest.mark.asyncio
async def test_publish_then_get_round_trip_and_republishing_replaces_the_document():
    rules_repo = InMemoryRulesRepository()
    handler, _ = publisher(rules_repo)
    reader = getter(rules_repo)

    first = await handler.execute(PublishRulesCommand(content=rules(config_updated_at="2026-09-01")))
    got = await reader.execute(GetRulesCommand())
    assert got.content == rules(config_updated_at="2026-09-01")
    assert got.published_at == first.published_at

    second = await handler.execute(PublishRulesCommand(content=rules(config_updated_at="2026-09-20")))
    got = await reader.execute(GetRulesCommand())
    assert got.content["config_updated_at"] == "2026-09-20"
    assert got.published_at == second.published_at


@pytest.mark.asyncio
async def test_the_stored_document_is_not_aliased_to_the_callers_dict():
    handler, repo = publisher()
    content = rules()

    await handler.execute(PublishRulesCommand(content=content))
    content["lanes"].append(lane(id="late"))

    assert len((await repo.get())["content"]["lanes"]) == 1


# -- get: nothing published yet ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_before_anything_is_published_returns_no_document_but_still_the_stats():
    application_repo = InMemoryApplicationRepository()
    application_repo.add(make_application(group="ai_engineer", discovery_queries=["line A"]))

    result = await getter(application_repo=application_repo).execute(GetRulesCommand())

    assert result.content is None
    assert result.published_at is None
    assert result.line_stats == {"line A": {"surfaced": 1, "approved": 0, "rejected": 0, "applied": 0}}
    assert result.lane_stats["ai_engineer"]["total"] == 1


@pytest.mark.asyncio
async def test_get_with_no_roles_returns_empty_stat_maps():
    result = await getter().execute(GetRulesCommand())

    assert (result.content, result.published_at, result.line_stats, result.lane_stats) == (None, None, {}, {})


# -- line_stats -------------------------------------------------------------------


def roles_for_line_stats():
    return [
        make_application(discovery_queries=["line A", "line B"], status=Status.APPROVED),
        make_application(discovery_queries=["line A"], status=Status.REJECTED),
        # Rejected, but he applied anyway: that is an approval and an application, not a rejection.
        make_application(
            discovery_queries=["line A"], status=Status.REJECTED, application_stage=Stage.APPLIED
        ),
        # No discovery_queries: credited to found_by_query instead.
        make_application(discovery_queries=[], found_by_query="line C", status=Status.TO_VALIDATE),
        # Nothing to credit at all.
        make_application(discovery_queries=[], found_by_query=None, status=Status.APPROVED),
        # Advanced stages count as approved and applied whatever the status says.
        make_application(
            discovery_queries=["line B"], status=Status.COLD, application_stage=Stage.INTERVIEWING
        ),
        # Closed is not an advanced stage: approved by status, but not "applied".
        make_application(discovery_queries=["line B"], status=Status.APPROVED, application_stage=Stage.CLOSED),
        make_application(discovery_queries=["line B"], status=Status.FLAGGED, application_stage=Stage.OFFER),
        # Archived roles still count for the line that found them.
        make_application(discovery_queries=["line A"], status=Status.REJECTED, archived_at=NOW),
        make_application(discovery_queries=["line D"], status=Status.DROPPED),
    ]


def test_line_stats_arithmetic_over_hand_built_roles():
    assert line_stats(roles_for_line_stats()) == {
        "line A": {"surfaced": 4, "approved": 2, "rejected": 2, "applied": 1},
        "line B": {"surfaced": 4, "approved": 4, "rejected": 0, "applied": 2},
        "line C": {"surfaced": 1, "approved": 0, "rejected": 0, "applied": 0},
        "line D": {"surfaced": 1, "approved": 0, "rejected": 0, "applied": 0},
    }


def test_line_stats_always_carries_all_four_counters_even_when_zero():
    stats = line_stats([make_application(discovery_queries=["only line"])])

    assert stats == {"only line": {"surfaced": 1, "approved": 0, "rejected": 0, "applied": 0}}
    assert list(stats["only line"]) == ["surfaced", "approved", "rejected", "applied"]


def test_line_stats_of_nothing_is_empty():
    assert line_stats([]) == {}
    assert line_stats([make_application(discovery_queries=[], found_by_query=None)]) == {}


def test_line_stats_agrees_with_the_feedback_definition_of_a_verdict():
    """The same roles through GetFeedback's query_performance, restricted to the keys they
    share, must give the same numbers: GetRules reuses that definition on purpose."""
    roles = roles_for_line_stats()
    feedback = query_performance(roles)
    ours = line_stats(roles)

    for line, counts in feedback.items():
        assert {k: ours[line][k] for k in counts} == counts


# -- lane_stats -------------------------------------------------------------------


def roles_for_lane_stats():
    ai = {"group": "ai_engineer"}
    return [
        make_application(status=Status.TO_VALIDATE, **ai),                                          # to_review
        make_application(status=Status.TO_VALIDATE, **ai),                                          # to_review
        make_application(status=Status.FLAGGED, **ai),                                              # flagged
        make_application(status=Status.FLAGGED, application_stage=Stage.APPLIED, **ai),            # approved, applied
        make_application(status=Status.APPROVED, **ai),                                             # approved
        make_application(status=Status.REJECTED, **ai),                                             # rejected
        make_application(status=Status.REJECTED, application_stage=Stage.INTERVIEWING, **ai),      # approved, applied
        make_application(status=Status.TO_VALIDATE, application_stage=Stage.CLOSED, **ai),         # total only
        make_application(status=Status.DROPPED, **ai),                                              # total only
        make_application(status=Status.COLD, **ai),                                                 # total only
        make_application(status=Status.TO_VALIDATE, archived_at=NOW, **ai),                         # skipped
        make_application(status=Status.APPROVED, application_stage=Stage.OFFER, group="founding_engineer"),
        make_application(status=Status.TO_VALIDATE, group="founding_engineer"),
        make_application(status=Status.TO_VALIDATE, group=None),
        make_application(status=Status.REJECTED, group=None),
    ]


def test_lane_stats_arithmetic_over_hand_built_roles():
    assert lane_stats(roles_for_lane_stats()) == {
        "ai_engineer": {"total": 10, "to_review": 2, "flagged": 1, "approved": 3, "applied": 2, "rejected": 1},
        "founding_engineer": {"total": 2, "to_review": 1, "flagged": 0, "approved": 1, "applied": 1, "rejected": 0},
        "unknown": {"total": 2, "to_review": 1, "flagged": 0, "approved": 0, "applied": 0, "rejected": 1},
    }


def test_lane_stats_carries_all_six_counters_in_order():
    stats = lane_stats([make_application(group="ai_engineer")])

    assert list(stats["ai_engineer"]) == ["total", "to_review", "flagged", "approved", "applied", "rejected"]


def test_lane_stats_skips_archived_roles_entirely_even_a_whole_lane_of_them():
    roles = [
        make_application(group="ai_engineer", archived_at=NOW),
        make_application(group="founding_engineer"),
    ]

    assert set(lane_stats(roles)) == {"founding_engineer"}


def test_archived_roles_count_in_line_stats_but_not_in_lane_stats():
    archived = make_application(
        group="ai_engineer", discovery_queries=["line A"], status=Status.REJECTED, archived_at=NOW
    )

    assert line_stats([archived]) == {"line A": {"surfaced": 1, "approved": 0, "rejected": 1, "applied": 0}}
    assert lane_stats([archived]) == {}


# -- get: stats are computed from the roles at read time --------------------------


@pytest.mark.asyncio
async def test_get_computes_both_stat_maps_from_the_roles_as_they_are_now():
    application_repo = InMemoryApplicationRepository()
    rules_repo = InMemoryRulesRepository()
    mover = make_application(group="ai_engineer", discovery_queries=["line A"], status=Status.TO_VALIDATE)
    archived = make_application(
        group="ai_engineer", discovery_queries=["line A"], status=Status.REJECTED, archived_at=NOW
    )
    application_repo.add(mover, archived)
    await rules_repo.publish(rules())
    reader = getter(rules_repo, application_repo)

    before = await reader.execute(GetRulesCommand())
    assert before.line_stats == {"line A": {"surfaced": 2, "approved": 0, "rejected": 1, "applied": 0}}
    assert before.lane_stats == {
        "ai_engineer": {"total": 1, "to_review": 1, "flagged": 0, "approved": 0, "applied": 0, "rejected": 0}
    }

    moved = application_repo.by_id(str(mover.id))
    moved.set_status(Status.APPROVED)
    moved.set_stage(Stage.APPLIED)
    await application_repo.update(moved)

    after = await reader.execute(GetRulesCommand())
    assert after.content == rules()  # the stored document did not change
    assert after.line_stats == {"line A": {"surfaced": 2, "approved": 1, "rejected": 1, "applied": 1}}
    assert after.lane_stats == {
        "ai_engineer": {"total": 1, "to_review": 0, "flagged": 0, "approved": 1, "applied": 1, "rejected": 0}
    }
