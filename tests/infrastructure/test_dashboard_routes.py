"""Dashboard routes end to end through FastAPI, with every Supabase-backed dependency
swapped for the in-memory fakes. A minimal app (just the dashboard router): importing
backend.infrastructure.main would run its lifespan, which needs real API keys."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domain.applications.skill_match import normalize_skill_match
from backend.domain.applications.value_objects import Stage, Status
from backend.infrastructure.adapters.driver.rest.dashboard_controller import router as dashboard_router
from backend.infrastructure.config.dependencies import (
    get_application_repository,
    get_login_attempt_repository,
    get_search_rules_repository,
    get_search_run_repository,
)
from backend.infrastructure.config.settings import Settings, get_settings
from tests.support.builders import make_application, skill_match_payload, skill_match_row
from tests.support.in_memory import (
    InMemoryApplicationRepository,
    InMemoryLoginAttemptRepository,
    InMemoryRulesRepository,
    InMemoryRunRepository,
)

PASSWORD = "test-dashboard-password"
TOKEN_SECRET = "test-token-secret-with-at-least-32-bytes-0123456789"
INGEST_KEY = "test-ingest-key"
INGEST = {"X-Ingest-Key": INGEST_KEY}
BASE = "/api/dashboard"


class Api:
    """The TestClient plus the fakes behind it, so tests can seed and inspect state."""

    def __init__(self, client, applications, runs, rules, attempts):
        self.client = client
        self.applications = applications
        self.runs = runs
        self.rules = rules
        self.attempts = attempts

    def login(self, device_id="test-device"):
        response = self.client.post(f"{BASE}/auth/login", json={"password": PASSWORD, "device_id": device_id})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr("backend.application.auth.login.handler._WRONG_PASSWORD_DELAY_SECONDS", 0)
    settings = Settings(
        _env_file=None,  # never read a real .env
        dashboard_password=PASSWORD,
        dashboard_token_secret=TOKEN_SECRET,
        dashboard_ingest_key=INGEST_KEY,
    )
    applications = InMemoryApplicationRepository()
    runs = InMemoryRunRepository()
    rules = InMemoryRulesRepository()
    attempts = InMemoryLoginAttemptRepository()

    app = FastAPI()
    app.include_router(dashboard_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_application_repository] = lambda: applications
    app.dependency_overrides[get_search_run_repository] = lambda: runs
    app.dependency_overrides[get_search_rules_repository] = lambda: rules
    app.dependency_overrides[get_login_attempt_repository] = lambda: attempts

    with TestClient(app) as client:
        yield Api(client, applications, runs, rules, attempts)


def analysed_role(api, **overrides):
    application = make_application(group="ai_engineer", score=88, **overrides)
    application.set_skill_match(normalize_skill_match(skill_match_payload()))
    api.applications.add(application)
    return application


def valid_rules():
    return {
        "schema_version": 1,
        "config_updated_at": "2026-09-17",
        "lanes": [
            {"id": "ai_engineer", "label": "AI Engineer", "lines": [{"line": "line A"}, {"line": "line B"}]},
            {"id": "founding_engineer", "label": "Founding Engineer", "lines": [{"line": "line C"}]},
        ],
    }


# -- auth -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/applications",
        f"/applications/{uuid4()}",
        "/rules",
        "/metrics",
        "/runs",
        "/feedback",
        "/auth/me",
    ],
)
def test_dashboard_reads_without_a_bearer_token_are_401(api, path):
    response = api.client.get(BASE + path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing bearer token"}


def test_a_garbage_token_or_one_signed_with_another_secret_is_401(api):
    forged = jwt.encode(
        {"device_id": "x", "exp": datetime.now(tz=timezone.utc) + timedelta(days=1)},
        "another-secret-that-is-also-long-enough-0123456789",
        algorithm="HS256",
    )

    for token in ("not-a-token", forged):
        response = api.client.get(f"{BASE}/rules", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/skill-match", {"items": []}),
        ("/rules", {"rules": valid_rules()}),
    ],
)
def test_ingest_routes_need_the_ingest_key_and_a_bearer_token_is_not_enough(api, path, body):
    bearer = api.login()

    without_key = api.client.post(BASE + path, json=body)
    wrong_key = api.client.post(BASE + path, json=body, headers={"X-Ingest-Key": "wrong"})
    bearer_only = api.client.post(BASE + path, json=body, headers=bearer)

    for response in (without_key, wrong_key, bearer_only):
        assert response.status_code == 401
        assert response.json() == {"detail": "Missing or invalid X-Ingest-Key"}


def test_a_rejected_publish_leaves_nothing_stored(api):
    api.client.post(f"{BASE}/rules", json={"rules": valid_rules()})  # no key

    assert api.rules.peek() is None


def test_login_with_the_right_password_unlocks_the_api_and_a_wrong_one_does_not(api):
    wrong = api.client.post(f"{BASE}/auth/login", json={"password": "nope", "device_id": "dev-1"})
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "Wrong password"}

    headers = api.login("dev-1")
    me = api.client.get(f"{BASE}/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {"device_id": "dev-1"}
    assert [a["success"] for a in api.attempts.attempts] == [False, True]


# -- skill_match on the read endpoints ---------------------------------------------


def test_list_returns_a_light_skill_match_and_detail_returns_the_whole_table(api):
    analysed = analysed_role(api)
    plain = make_application(group="ai_engineer")
    api.applications.add(plain)
    headers = api.login()

    listed = api.client.get(f"{BASE}/applications", headers=headers)
    assert listed.status_code == 200
    by_id = {a["id"]: a for a in listed.json()["applications"]}

    light = by_id[str(analysed.id)]["skill_match"]
    assert "rows" not in light
    assert set(light) == {"version", "analyzed_on", "verdict", "cv_used", "linkedin_used", "jd_source", "summary"}
    assert light["summary"]["requirements"] == 2
    assert by_id[str(plain.id)]["skill_match"] == {}

    detail = api.client.get(f"{BASE}/applications/{analysed.id}", headers=headers)
    assert detail.status_code == 200
    full = detail.json()["skill_match"]
    assert len(full["rows"]) == 2
    assert full["rows"][0]["linkedin"] == {
        "level": "partial", "evidence": None, "fix": "Add FastAPI to the Skills list.",
    }
    assert {k: v for k, v in full.items() if k != "rows"} == light

    # The light projection is a view: listing did not strip anything from the stored table.
    assert len(api.applications.by_id(str(analysed.id)).skill_match["rows"]) == 2


def test_list_filters_and_default_sort_work_through_the_fake(api):
    older = make_application(title="Older", group="ai_engineer", posted_date="2026-09-01")
    newer = make_application(title="Newer", group="ai_engineer", posted_date="2026-09-20")
    other = make_application(title="Other lane", group="founding_engineer", posted_date="2026-09-10")
    api.applications.add(older, newer, other)
    headers = api.login()

    everything = api.client.get(f"{BASE}/applications", headers=headers).json()["applications"]
    assert [a["title"] for a in everything] == ["Newer", "Other lane", "Older"]

    only_ai = api.client.get(f"{BASE}/applications", params={"group": "ai_engineer"}, headers=headers)
    assert [a["title"] for a in only_ai.json()["applications"]] == ["Newer", "Older"]


# -- POST /skill-match ------------------------------------------------------------


def test_post_skill_match_stores_matches_and_reports_unmatched_and_invalid(api):
    by_id = make_application(group="ai_engineer")
    by_url = make_application(
        group="ai_engineer",
        jd_url="https://jobs.example.com/jobs/view/7001",
        postings=[{"id": "7001", "url": "https://jobs.example.com/jobs/view/7001"}],
    )
    broken = make_application(group="ai_engineer")
    api.applications.add(by_id, by_url, broken)
    missing_id = str(uuid4())

    response = api.client.post(
        f"{BASE}/skill-match",
        headers=INGEST,
        json={
            "items": [
                {"application_id": str(by_id.id), "skill_match": skill_match_payload(verdict="by id")},
                {"jd_url": "https://jobs.example.com/jobs/view/7001?tracking=x", "skill_match": skill_match_payload(verdict="by url")},
                {"application_id": missing_id, "skill_match": skill_match_payload()},
                {
                    "application_id": str(broken.id),
                    "skill_match": {"rows": [skill_match_row(match="excellent")]},
                },
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] == 3
    assert body["updated"] == 2
    assert body["unmatched"] == [missing_id]
    assert len(body["invalid"]) == 1
    assert body["invalid"][0].startswith(f"{broken.id}: rows[0].match.level must be one of strong, partial, gap")
    assert set(body) == {"matched", "updated", "unmatched", "invalid"}

    headers = api.login()
    detail = api.client.get(f"{BASE}/applications/{by_id.id}", headers=headers).json()
    assert detail["skill_match"]["verdict"] == "by id"
    assert detail["skill_match"]["summary"]["to_surface"] == 1
    assert api.client.get(f"{BASE}/applications/{by_url.id}", headers=headers).json()["skill_match"]["verdict"] == "by url"
    assert api.client.get(f"{BASE}/applications/{broken.id}", headers=headers).json()["skill_match"] == {}
    assert detail["reviewed_at"] is None  # an agent write is not a review


def test_post_skill_match_null_or_empty_object_clears_the_table(api):
    first = analysed_role(api)
    second = analysed_role(api)

    response = api.client.post(
        f"{BASE}/skill-match",
        headers=INGEST,
        json={
            "items": [
                {"application_id": str(first.id), "skill_match": None},
                {"application_id": str(second.id), "skill_match": {}},
            ]
        },
    )

    assert response.json() == {"matched": 2, "updated": 2, "unmatched": [], "invalid": []}
    assert api.applications.by_id(str(first.id)).skill_match == {}
    assert api.applications.by_id(str(second.id)).skill_match == {}


def test_post_skill_match_requires_the_skill_match_key_so_a_forgotten_payload_cannot_clear_a_table(api):
    target = analysed_role(api)

    missing_key = api.client.post(
        f"{BASE}/skill-match", headers=INGEST, json={"items": [{"application_id": str(target.id)}]}
    )

    assert missing_key.status_code == 422
    assert api.applications.by_id(str(target.id)).skill_match["rows"]


def test_post_skill_match_reports_a_payload_that_is_not_an_object_without_failing_the_batch(api):
    broken = analysed_role(api)
    good = make_application(group="ai_engineer")
    api.applications.add(good)
    kept = api.applications.by_id(str(broken.id)).skill_match

    response = api.client.post(
        f"{BASE}/skill-match",
        headers=INGEST,
        json={
            "items": [
                {"application_id": str(broken.id), "skill_match": "not an object"},
                {"application_id": str(good.id), "skill_match": skill_match_payload(verdict="still applied")},
                {"application_id": str(broken.id), "skill_match": ["a", "list"]},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["matched"], body["updated"], body["unmatched"]) == (3, 1, [])
    assert body["invalid"] == [f"{broken.id}: skill_match must be an object"] * 2
    assert api.applications.by_id(str(broken.id)).skill_match == kept  # the old table is left alone
    assert api.applications.by_id(str(good.id)).skill_match["verdict"] == "still applied"


# -- the other writers keep the table ----------------------------------------------


def test_patch_still_works_returns_the_whole_table_and_keeps_it(api):
    target = analysed_role(api)
    headers = api.login()

    response = api.client.patch(
        f"{BASE}/applications/{target.id}", headers=headers, json={"status": "Approved", "notes": "looks good"}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["notes"]) == ("Approved", "looks good")
    assert body["reviewed_at"] is not None  # the human path marks it reviewed
    assert len(body["skill_match"]["rows"]) == 2
    stored = api.applications.by_id(str(target.id))
    assert stored.status == Status.APPROVED
    assert stored.skill_match == normalize_skill_match(skill_match_payload())


def test_patch_on_an_unknown_role_is_404(api):
    response = api.client.patch(f"{BASE}/applications/{uuid4()}", headers=api.login(), json={"status": "Approved"})

    assert response.status_code == 404


def test_create_application_returns_an_empty_skill_match(api):
    response = api.client.post(
        f"{BASE}/applications", headers=api.login(), json={"title": "Staff Engineer", "company": "Acme Robotics"}
    )

    assert response.status_code == 201
    assert response.json()["skill_match"] == {}


def test_contact_stage_update_returns_the_whole_table(api):
    target = analysed_role(api, contacts=[{"id": "c1", "name": "Alex Demo", "outreach_stage": None}])

    response = api.client.patch(
        f"{BASE}/applications/{target.id}/contacts/c1", headers=api.login(), json={"stage": "Sent"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contacts"][0]["outreach_stage"] == "Sent"
    assert len(body["skill_match"]["rows"]) == 2


def test_an_ingest_repost_through_the_api_keeps_the_table(api):
    role = {
        "id": "4001", "title": "Applied AI Engineer", "company": "Acme AI", "group": "ai_engineer",
        "score": 82, "jd_url": "https://jobs.example.com/jobs/view/4001", "source": "linkedin",
        "run_date": "2026-09-17",
    }
    first = api.client.post(f"{BASE}/ingest", headers=INGEST, json={"roles": [role]})
    assert first.json()["added"] == 1
    (stored,) = api.applications.all()
    api.client.post(
        f"{BASE}/skill-match",
        headers=INGEST,
        json={"items": [{"application_id": str(stored.id), "skill_match": skill_match_payload()}]},
    )

    repost = api.client.post(
        f"{BASE}/ingest",
        headers=INGEST,
        json={"roles": [{**role, "id": "4002", "jd_url": "https://jobs.example.com/jobs/view/4002"}]},
    )

    assert (repost.json()["added"], repost.json()["updated"]) == (0, 1)
    (after,) = api.applications.all()
    assert len(after.postings) == 2
    assert after.skill_match == normalize_skill_match(skill_match_payload())


# -- /rules -----------------------------------------------------------------------


def test_post_rules_with_an_invalid_document_is_422_with_the_message_as_detail(api):
    response = api.client.post(
        f"{BASE}/rules", headers=INGEST, json={"rules": {"schema_version": 1, "lanes": []}}
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "lanes must be a non-empty list"}
    assert api.rules.peek() is None


@pytest.mark.parametrize(
    ("document", "detail"),
    [
        ({"lanes": [{"id": "a", "label": "A", "lines": []}]}, "schema_version must be an integer"),
        ({"schema_version": 1, "lanes": [{"id": "a", "label": "", "lines": []}]}, "lanes[0].label must be a non-empty string"),
        ({"schema_version": 1, "lanes": [{"id": "a", "label": "A"}]}, "lanes[0].lines must be a list"),
    ],
)
def test_post_rules_reports_which_part_is_wrong(api, document, detail):
    response = api.client.post(f"{BASE}/rules", headers=INGEST, json={"rules": document})

    assert (response.status_code, response.json()["detail"]) == (422, detail)


def test_post_rules_without_a_rules_object_is_a_422_from_request_validation(api):
    for body in ({}, {"rules": "text"}, {"rules": [1]}):
        assert api.client.post(f"{BASE}/rules", headers=INGEST, json=body).status_code == 422


def test_get_rules_before_and_after_publishing(api):
    api.applications.add(
        make_application(group="ai_engineer", discovery_queries=["line A"], status=Status.APPROVED),
        make_application(group="ai_engineer", discovery_queries=["line A", "line B"], status=Status.REJECTED),
        make_application(group="founding_engineer", discovery_queries=["line C"], application_stage=Stage.APPLIED),
        make_application(group=None, status=Status.FLAGGED),
    )
    headers = api.login()

    before = api.client.get(f"{BASE}/rules", headers=headers)
    assert before.status_code == 200
    assert before.json()["published_at"] is None
    assert before.json()["content"] is None
    assert before.json()["line_stats"]["line A"] == {"surfaced": 2, "approved": 1, "rejected": 1, "applied": 0}
    assert before.json()["lane_stats"]["unknown"]["flagged"] == 1

    published = api.client.post(f"{BASE}/rules", headers=INGEST, json={"rules": valid_rules()})
    assert published.status_code == 200
    assert set(published.json()) == {"published_at", "lanes", "lines"}
    assert (published.json()["lanes"], published.json()["lines"]) == (2, 3)

    after = api.client.get(f"{BASE}/rules", headers=headers)
    body = after.json()
    assert set(body) == {"published_at", "content", "line_stats", "lane_stats"}
    assert body["content"] == valid_rules()
    assert body["published_at"] == published.json()["published_at"]
    assert body["line_stats"] == before.json()["line_stats"]
    assert body["lane_stats"]["founding_engineer"] == {
        "total": 1, "to_review": 0, "flagged": 0, "approved": 1, "applied": 1, "rejected": 0,
    }


def test_republishing_replaces_the_document(api):
    headers = api.login()
    api.client.post(f"{BASE}/rules", headers=INGEST, json={"rules": valid_rules()})
    newer = {**valid_rules(), "config_updated_at": "2026-09-30"}

    second = api.client.post(f"{BASE}/rules", headers=INGEST, json={"rules": newer})

    body = api.client.get(f"{BASE}/rules", headers=headers).json()
    assert body["content"]["config_updated_at"] == "2026-09-30"
    assert body["published_at"] == second.json()["published_at"]


def test_rules_stats_follow_a_review_made_through_the_api(api):
    target = make_application(group="ai_engineer", discovery_queries=["line A"], status=Status.TO_VALIDATE)
    api.applications.add(target)
    headers = api.login()
    assert api.client.get(f"{BASE}/rules", headers=headers).json()["lane_stats"]["ai_engineer"]["to_review"] == 1

    api.client.patch(f"{BASE}/applications/{target.id}", headers=headers, json={"stage": "Applied"})

    body = api.client.get(f"{BASE}/rules", headers=headers).json()
    assert body["lane_stats"]["ai_engineer"]["to_review"] == 0
    assert body["lane_stats"]["ai_engineer"]["applied"] == 1
    assert body["line_stats"]["line A"] == {"surfaced": 1, "approved": 1, "rejected": 0, "applied": 1}
