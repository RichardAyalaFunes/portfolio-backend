"""Search feedback loop tests: reviewed_at is set only by Richard's paths, ingest
carries the new lane/query/tag fields, and GetFeedback returns what the agent
needs. Fake in-memory repositories -- no network."""

import copy
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.application.applications.annotate.command import AnnotateCommand, AnnotateItem
from backend.application.applications.annotate.handler import AnnotateHandler
from backend.application.applications.get_feedback.command import GetFeedbackCommand
from backend.application.applications.get_feedback.handler import GetFeedbackHandler
from backend.application.applications.ingest_batch.command import IngestBatchCommand
from backend.application.applications.ingest_batch.handler import IngestBatchHandler
from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.ports.search_run_repository import ISearchRunRepository
from backend.application.applications.update_application.command import UpdateApplicationCommand
from backend.application.applications.update_application.handler import UpdateApplicationHandler
from backend.domain.applications.value_objects import Status


class FakeApplicationRepository(IJobApplicationRepository):
    def __init__(self) -> None:
        self.rows = {}

    async def list(self, *, include_archived=False, **_filters):
        return [copy.deepcopy(a) for a in self.rows.values() if include_archived or not a.is_archived]

    async def get(self, application_id):
        row = self.rows.get(str(application_id))
        return copy.deepcopy(row) if row else None

    async def get_by_identity_key(self, identity_key):
        return next((copy.deepcopy(a) for a in self.rows.values() if a.identity_key == identity_key), None)

    async def create(self, application):
        self.rows[str(application.id)] = copy.deepcopy(application)
        return copy.deepcopy(application)

    async def update(self, application):
        self.rows[str(application.id)] = copy.deepcopy(application)
        return copy.deepcopy(application)

    async def save_skill_match(self, application):
        self.rows[str(application.id)].skill_match = copy.deepcopy(application.skill_match)


class FakeRunRepository(ISearchRunRepository):
    def __init__(self, runs=None) -> None:
        self.runs = runs or []

    async def list_all(self):
        return sorted(self.runs, key=lambda r: r["run_date"], reverse=True)

    async def upsert(self, run):
        self.runs = [r for r in self.runs if r["run_date"] != run["run_date"]] + [run]


def role(**overrides):
    base = {
        "id": "4001",
        "title": "Applied AI Engineer",
        "company": "Acme AI",
        "group": "ai_engineer",
        "score": 82,
        "jd_url": "https://www.linkedin.com/jobs/view/4001",
        "source": "linkedin",
        "run_date": "2026-09-17",
    }
    base.update(overrides)
    return base


async def ingest(repo, *roles):
    return await IngestBatchHandler(repository=repo).execute(IngestBatchCommand(roles=list(roles)))


@pytest.mark.asyncio
async def test_ingest_stores_lanes_queries_and_normalized_tags_without_marking_reviewed():
    repo = FakeApplicationRepository()
    await ingest(repo, role(
        secondary_lanes=["founding_engineer"],
        discovery_queries=['"applied ai engineer" @south_america'],
        tags=["Location unsure", "big-corporate"],
    ))

    (stored,) = repo.rows.values()
    assert stored.secondary_lanes == ["founding_engineer"]
    assert stored.discovery_queries == ['"applied ai engineer" @south_america']
    assert stored.tags == ["location_unsure", "big_corporate"]
    assert stored.reviewed_at is None


@pytest.mark.asyncio
async def test_found_by_query_backfills_discovery_queries():
    repo = FakeApplicationRepository()
    await ingest(repo, role(found_by_query='"ai engineer" @peru'))

    (stored,) = repo.rows.values()
    assert stored.discovery_queries == ['"ai engineer" @peru']


@pytest.mark.asyncio
async def test_repost_unions_queries_replaces_tags_and_keeps_richards_verdict():
    repo = FakeApplicationRepository()
    await ingest(repo, role(discovery_queries=["line A"], tags=["location_unsure"]))
    (row_id,) = repo.rows
    await UpdateApplicationHandler(repository=repo).execute(
        UpdateApplicationCommand(application_id=row_id, status="Approved", notes="good one")
    )

    await ingest(repo, role(id="4002", jd_url="https://www.linkedin.com/jobs/view/4002",
                            discovery_queries=["line B", "line A"], tags=[]))

    (stored,) = repo.rows.values()
    assert stored.discovery_queries == ["line A", "line B"]
    assert stored.tags == []
    assert stored.status == Status.APPROVED
    assert stored.notes == "good one"


@pytest.mark.asyncio
async def test_repost_without_tags_key_keeps_existing_tags():
    repo = FakeApplicationRepository()
    await ingest(repo, role(tags=["big_corporate"]))
    await ingest(repo, role(id="4002", jd_url="https://www.linkedin.com/jobs/view/4002"))

    (stored,) = repo.rows.values()
    assert stored.tags == ["big_corporate"]


@pytest.mark.asyncio
async def test_dashboard_edit_marks_reviewed_but_url_fix_does_not():
    repo = FakeApplicationRepository()
    await ingest(repo, role())
    (row_id,) = repo.rows
    handler = UpdateApplicationHandler(repository=repo)

    await handler.execute(UpdateApplicationCommand(application_id=row_id, jd_url="https://x.test/job"))
    assert repo.rows[row_id].reviewed_at is None

    await handler.execute(UpdateApplicationCommand(application_id=row_id, stage="Applied"))
    assert repo.rows[row_id].reviewed_at is not None


@pytest.mark.asyncio
async def test_annotate_marks_reviewed():
    repo = FakeApplicationRepository()
    await ingest(repo, role())
    await AnnotateHandler(repository=repo).execute(
        AnnotateCommand(items=[AnnotateItem(url="https://www.linkedin.com/jobs/view/4001", note="on-site, no")])
    )

    (stored,) = repo.rows.values()
    assert stored.reviewed_at is not None
    assert stored.notes == "on-site, no"


@pytest.mark.asyncio
async def test_feedback_defaults_to_latest_run_and_reports_verdicts_per_query():
    repo = FakeApplicationRepository()
    await ingest(
        repo,
        role(discovery_queries=["line A"], score=70),
        role(id="5001", title="Founding Engineer", company="Beta", jd_url="https://www.linkedin.com/jobs/view/5001",
             group="founding_engineer", score=90, discovery_queries=["line A", "line B"], tags=["salary_unknown"]),
        role(id="6001", title="Backend Engineer", company="Gamma", jd_url="https://www.linkedin.com/jobs/view/6001",
             discovery_queries=["line B"]),
    )
    ids = {a.company: str(a.id) for a in repo.rows.values()}
    update = UpdateApplicationHandler(repository=repo)
    await update.execute(UpdateApplicationCommand(application_id=ids["Acme AI"], status="Approved"))
    await update.execute(UpdateApplicationCommand(application_id=ids["Beta"], status="Rejected", notes="8+ years"))

    # A review from before the last run must not appear.
    stale = repo.rows[ids["Gamma"]]
    stale.status = Status.REJECTED
    stale.reviewed_at = datetime.now(tz=timezone.utc) - timedelta(days=10)

    runs = FakeRunRepository([
        {"run_date": (date.today() - timedelta(days=20)).isoformat()},
        {"run_date": (date.today() - timedelta(days=2)).isoformat(), "outcome": {"passed": 1}},
    ])
    result = await GetFeedbackHandler(repository=repo, run_repository=runs).execute(GetFeedbackCommand())

    assert result.since_source == "latest_run"
    assert result.since == date.today() - timedelta(days=2)
    assert [r["company"] for r in result.reviewed] == ["Beta", "Acme AI"]
    assert result.reviewed[0]["notes"] == "8+ years"
    assert result.summary["by_status"] == {"Rejected": 1, "Approved": 1}
    assert result.summary["tags_on_rejected"] == {"salary_unknown": 1}
    # All-time per line: the stale review still counts here.
    assert result.query_performance["line A"] == {"surfaced": 2, "approved": 1, "rejected": 1}
    assert result.query_performance["line B"] == {"surfaced": 2, "rejected": 2}
    assert [d["company"] for d in result.disagreements["approved_below_bar"]] == ["Acme AI"]
    assert [d["company"] for d in result.disagreements["rejected_high_score"]] == ["Beta"]
    assert result.recent_runs[0]["outcome"] == {"passed": 1}


@pytest.mark.asyncio
async def test_feedback_without_runs_uses_default_window_and_explicit_since_wins():
    repo = FakeApplicationRepository()
    handler = GetFeedbackHandler(repository=repo, run_repository=FakeRunRepository())

    default = await handler.execute(GetFeedbackCommand())
    assert default.since_source == "default_window"
    assert default.since == date.today() - timedelta(days=30)

    explicit = await handler.execute(GetFeedbackCommand(since=date(2026, 9, 1)))
    assert (explicit.since, explicit.since_source) == (date(2026, 9, 1), "request")
