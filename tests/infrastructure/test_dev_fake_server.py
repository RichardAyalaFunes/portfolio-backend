"""Smoke tests for scripts/dev_fake_server.py: it builds offline, serves the seeded
data behind the documented fake credentials, and its seeds stay valid against the
real validators -- so the UI keeps getting a faithful fake as the contract evolves."""

import importlib.util
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.application.applications.get_rules.handler import line_stats
from backend.application.applications.publish_rules.handler import validate_rules
from backend.domain.applications.skill_match import normalize_skill_match
from backend.domain.applications.value_objects import Stage, Status

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_fake_server.py"
BASE = "/api/dashboard"


@pytest.fixture(scope="module")
def fake():
    spec = importlib.util.spec_from_file_location("dev_fake_server", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(fake, monkeypatch):
    for name in ("FAKE_DASHBOARD_PASSWORD", "FAKE_TOKEN_SECRET", "FAKE_INGEST_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("backend.application.auth.login.handler._WRONG_PASSWORD_DELAY_SECONDS", 0)
    with TestClient(fake.build_app()) as test_client:
        yield test_client


def login(client, password="fake-dashboard-password"):
    return client.post(f"{BASE}/auth/login", json={"password": password, "device_id": "dev-ui"})


def bearer(client):
    return {"Authorization": f"Bearer {login(client).json()['token']}"}


def visible(roles):
    return [r for r in roles if not r.is_archived]


# -- the seed data ----------------------------------------------------------------


def test_seeded_roles_cover_every_state_the_ui_has_to_handle(fake):
    roles = fake.build_roles()
    shown = visible(roles)

    assert len(roles) == len({str(r.id) for r in roles}) == len({r.identity_key for r in roles})
    assert len(shown) == 40 and len(roles) - len(shown) == 1
    assert {r.status for r in shown} == set(Status)
    assert {r.application_stage for r in shown} == set(Stage)
    assert {r.live_state for r in shown} == {"LISTED", "CLOSED", "SUSPENDED", "GONE", "UNVERIFIABLE", None}
    assert {r.group for r in shown} >= {"ai_engineer", "forward_deployed_engineer", "founding_engineer"}
    assert any(r.secondary_lanes for r in shown)
    assert {t for r in shown for t in r.tags} == {
        "location_unsure", "company_type_unclear", "salary_unknown", "big_corporate", "language_mixed",
    }
    assert {r.drop_reason for r in shown if r.drop_reason} == {
        "below_bar", "eligibility_geo", "stack_paradigm", "off_lane", "deal_breaker", "staffing_pool",
    }
    below_bar = [r for r in shown if r.drop_reason == "below_bar"]
    assert all(
        (r.status, r.drop_stage, r.band) == (Status.DROPPED, "scored", "below") and 55 <= r.score <= 74
        for r in below_bar
    )
    assert any(r.score is not None and r.score >= 90 for r in shown)
    assert [r.company for r in shown if r.contacts] and all(r.score >= 80 for r in shown if r.contacts)
    assert {r.application_form["apply_type"] for r in shown if r.application_form} >= {"company_form"}

    ages = [(fake.TODAY - r.posted_date).days for r in shown]
    assert min(ages) == 0 and max(ages) >= 55


def test_only_synthetic_hosts_and_names_are_used(fake):
    for role in fake.build_roles():
        assert role.jd_url.startswith("https://") and ".example.com/" in role.jd_url
        for posting in role.postings:
            assert ".example.com/" in posting["url"]
        for contact in role.contacts:
            assert ".example.com/" in contact["linkedin_url"]


def test_two_roles_carry_a_realistic_skill_match_that_the_real_validator_accepts_unchanged(fake):
    analysed = [r for r in fake.build_roles() if r.skill_match]

    assert len(analysed) == 2
    for role in analysed:
        assert len(role.skill_match["rows"]) == 8
        assert normalize_skill_match(role.skill_match, today=fake.TODAY) == role.skill_match
        summary = role.skill_match["summary"]
        assert summary["match_strong"] and summary["match_partial"] and summary["match_gap"]
        assert summary["to_surface"] > 0
    assert {r.skill_match["jd_source"] for r in analysed} == {"full_text", "excerpt"}


def test_seeded_rules_document_is_valid_balanced_and_matches_the_roles(fake):
    rules = fake.build_rules()
    lanes, lines = validate_rules(rules)

    assert (lanes, lines) == (3, 15)
    for lane in rules["lanes"]:
        assert sum(item["weight"] for item in lane["rubric"]) == 100
        assert len(lane["rubric"]) == 6
        assert {item["status"] for item in lane["lines"]} <= {"standing", "trial", "weekly", "retired"}
        assert lane["rules"]
    assert {item["status"] for lane in rules["lanes"] for item in lane["lines"]} == {
        "standing", "trial", "weekly", "retired",
    }
    assert len(rules["gates"]) == 8
    assert rules["thresholds"]["pass_bar"] == 75

    stats = line_stats(fake.build_roles())
    published_lines = {item["line"] for lane in rules["lanes"] for item in lane["lines"]}
    assert len(published_lines & set(stats)) >= 14  # all but the retired line that never surfaced a role
    assert set(stats) - published_lines  # and one legacy line the document no longer lists


def test_seeded_runs_are_newest_first_material_for_the_feedback_endpoint(fake):
    runs = fake.build_runs()

    assert len(runs) == 10
    assert runs[0]["run_date"] == fake.TODAY.isoformat()
    assert runs[0]["outcome"] and runs[0]["line_yield"] and runs[0]["plan_changes"]
    assert Counter(bool(run["outcome"]) for run in runs) == {True: 3, False: 7}


# -- the running app ---------------------------------------------------------------


def test_login_with_the_documented_fake_password_unlocks_the_seeded_api(client):
    wrong = login(client, "not-the-password")
    assert wrong.status_code == 401

    headers = bearer(client)
    listed = client.get(f"{BASE}/applications", headers=headers)
    assert listed.status_code == 200
    applications = listed.json()["applications"]
    assert len(applications) == 40
    assert all("rows" not in a["skill_match"] for a in applications)
    analysed = [a for a in applications if a["skill_match"]]
    assert len(analysed) == 2

    detail = client.get(f"{BASE}/applications/{analysed[0]['id']}", headers=headers).json()
    assert len(detail["skill_match"]["rows"]) == 8

    rules = client.get(f"{BASE}/rules", headers=headers).json()
    assert rules["content"]["schema_version"] == 1
    assert rules["published_at"]
    assert rules["line_stats"] and rules["lane_stats"]["ai_engineer"]["total"] > 0

    for path in ("/metrics", "/runs", "/feedback"):
        assert client.get(BASE + path, headers=headers).status_code == 200


def test_the_documented_fake_ingest_key_works_and_a_wrong_one_does_not(client):
    headers = bearer(client)
    target = client.get(f"{BASE}/applications", headers=headers).json()["applications"][0]
    body = {"items": [{"application_id": target["id"], "skill_match": None}]}

    assert client.post(f"{BASE}/skill-match", json=body, headers={"X-Ingest-Key": "wrong"}).status_code == 401
    ok = client.post(f"{BASE}/skill-match", json=body, headers={"X-Ingest-Key": "fake-ingest-key"})
    assert ok.json() == {"matched": 1, "updated": 1, "unmatched": [], "invalid": []}


def test_credentials_can_be_overridden_with_environment_variables(fake, monkeypatch):
    monkeypatch.setenv("FAKE_DASHBOARD_PASSWORD", "another-fake-password")
    monkeypatch.setattr("backend.application.auth.login.handler._WRONG_PASSWORD_DELAY_SECONDS", 0)

    with TestClient(fake.build_app()) as client:
        assert login(client).status_code == 401
        assert login(client, "another-fake-password").status_code == 200


def test_an_empty_environment_variable_falls_back_to_the_fake_default_never_to_an_open_door(fake, monkeypatch):
    monkeypatch.setenv("FAKE_DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("FAKE_INGEST_KEY", "")
    monkeypatch.setattr("backend.application.auth.login.handler._WRONG_PASSWORD_DELAY_SECONDS", 0)

    with TestClient(fake.build_app()) as client:
        assert login(client, "").status_code == 401
        assert login(client).status_code == 200  # the documented default
        body = {"items": []}
        assert client.post(f"{BASE}/skill-match", json=body, headers={"X-Ingest-Key": ""}).status_code == 401
        assert client.post(f"{BASE}/skill-match", json=body, headers={"X-Ingest-Key": "fake-ingest-key"}).status_code == 200


def test_cors_allows_the_vite_dev_server_on_5174_and_no_other_origin(client):
    preflight = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}

    for origin in ("http://localhost:5174", "http://127.0.0.1:5174"):
        response = client.options(f"{BASE}/applications", headers={"Origin": origin, **preflight})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin

    other = client.options(f"{BASE}/applications", headers={"Origin": "http://localhost:5173", **preflight})
    assert "access-control-allow-origin" not in other.headers


def test_the_app_never_builds_a_supabase_client(fake, client):
    app = fake.build_app()
    refuse = app.dependency_overrides[fake.get_postgrest_client]

    with pytest.raises(RuntimeError, match="never talks to Supabase"):
        refuse()
    assert client.get("/health").json() == {"status": "ok", "mode": "fake-data"}
