"""Knowledge routes end to end through FastAPI, with the Supabase-backed repository swapped for the
in-memory fake. A minimal app (the dashboard router for login, plus the knowledge router)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infrastructure.adapters.driver.rest.dashboard_controller import router as dashboard_router
from backend.infrastructure.adapters.driver.rest.knowledge_controller import router as knowledge_router
from backend.infrastructure.config.dependencies import get_knowledge_repository, get_login_attempt_repository
from backend.infrastructure.config.settings import Settings, get_settings
from tests.support.in_memory import InMemoryKnowledgeRepository, InMemoryLoginAttemptRepository
from tests.support.knowledge_builders import make_document

PASSWORD = "test-dashboard-password"
TOKEN_SECRET = "test-token-secret-with-at-least-32-bytes-0123456789"
INGEST_KEY = "test-ingest-key"
INGEST = {"X-Ingest-Key": INGEST_KEY}
BASE = "/api/dashboard/knowledge"

IDEMPOTENCY = "reference/backend/idempotency"
DLQ = "reference/backend/dead-letter-queue"


class Api:
    def __init__(self, client, repository):
        self.client = client
        self.repository = repository

    def login(self):
        response = self.client.post(
            "/api/dashboard/auth/login", json={"password": PASSWORD, "device_id": "test-device"}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def publish(self, *documents):
        response = self.client.post(f"{BASE}/pages", json={"pages": list(documents)}, headers=INGEST)
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr("backend.application.auth.login.handler._WRONG_PASSWORD_DELAY_SECONDS", 0)
    settings = Settings(
        _env_file=None,
        dashboard_password=PASSWORD,
        dashboard_token_secret=TOKEN_SECRET,
        dashboard_ingest_key=INGEST_KEY,
    )
    repository = InMemoryKnowledgeRepository()
    app = FastAPI()
    app.include_router(dashboard_router)
    app.include_router(knowledge_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_knowledge_repository] = lambda: repository
    app.dependency_overrides[get_login_attempt_repository] = lambda: InMemoryLoginAttemptRepository()
    with TestClient(app) as client:
        yield Api(client, repository)


def two_pages():
    return [
        make_document(IDEMPOTENCY, links=[DLQ]),
        make_document(
            DLQ,
            title="Dead letter queue (DLQ)",
            aliases=["DLQ"],
            links=[IDEMPOTENCY],
            order=2,
            search_text="Dead letter queue (DLQ)\nDLQ\nA message that keeps failing is moved aside.",
        ),
    ]


# -- auth -------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", "/search?q=idem", f"/pages/{IDEMPOTENCY}"])
def test_every_read_requires_the_device_token(api, path):
    assert api.client.get(f"{BASE}{path}").status_code == 401
    assert api.client.get(f"{BASE}{path}", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_the_write_routes_need_the_ingest_key_and_a_device_token_is_not_enough(api):
    token = api.login()
    body = {"pages": two_pages()}

    assert api.client.post(f"{BASE}/pages", json=body).status_code == 401
    assert api.client.post(f"{BASE}/pages", json=body, headers=token).status_code == 401
    assert api.client.post(f"{BASE}/pages", json=body, headers={"X-Ingest-Key": "wrong"}).status_code == 401
    assert api.client.post(f"{BASE}/prune", json={"keep": [IDEMPOTENCY]}, headers=token).status_code == 401
    assert api.repository.slugs() == []


# -- publish and read ---------------------------------------------------------------


def test_published_pages_show_in_the_index_without_their_bodies(api):
    assert api.publish(*two_pages()) == {"upserted": 2}
    headers = api.login()

    response = api.client.get(BASE, headers=headers)

    assert response.status_code == 200
    pages = response.json()["pages"]
    assert [p["slug"] for p in pages] == [IDEMPOTENCY, DLQ]
    assert pages[0]["group"] == "Backend"
    assert pages[0]["read_minutes"] == 3
    assert "body" not in pages[0]


def test_a_page_comes_back_with_its_body_and_backlinks_using_a_slug_with_slashes(api):
    api.publish(*two_pages())

    response = api.client.get(f"{BASE}/pages/{IDEMPOTENCY}", headers=api.login())

    assert response.status_code == 200
    data = response.json()
    assert data["page"]["slug"] == IDEMPOTENCY
    assert data["page"]["body"]["blocks"][0]["tone"] == "lead"
    assert data["page"]["links"] == [DLQ]
    assert [b["slug"] for b in data["backlinks"]] == [DLQ]
    assert data["backlinks"][0]["title"] == "Dead letter queue (DLQ)"


def test_an_unknown_page_is_a_404(api):
    response = api.client.get(f"{BASE}/pages/reference/backend/nope", headers=api.login())

    assert response.status_code == 404


def test_an_invalid_document_is_a_422_that_names_the_page_and_stores_nothing(api):
    bad = make_document(DLQ, kind="essay")

    response = api.client.post(f"{BASE}/pages", json={"pages": [make_document(IDEMPOTENCY), bad]}, headers=INGEST)

    assert response.status_code == 422
    assert DLQ in response.json()["detail"]
    assert api.repository.slugs() == []


def test_a_script_tag_cannot_be_smuggled_in_as_a_block(api):
    hostile = make_document(IDEMPOTENCY)
    hostile["body"]["blocks"].append({"t": "html", "html": "<script>alert(1)</script>"})

    response = api.client.post(f"{BASE}/pages", json={"pages": [hostile]}, headers=INGEST)

    assert response.status_code == 422
    assert api.repository.slugs() == []


def test_republishing_replaces_a_page_in_place(api):
    api.publish(make_document(IDEMPOTENCY))
    api.publish(make_document(IDEMPOTENCY, title="Idempotency v2"))

    pages = api.client.get(BASE, headers=api.login()).json()["pages"]

    assert [p["title"] for p in pages] == ["Idempotency v2"]


# -- search -------------------------------------------------------------------------


def test_search_returns_ranked_results_with_a_snippet(api):
    api.publish(*two_pages())

    response = api.client.get(f"{BASE}/search", params={"q": "message failing"}, headers=api.login())

    assert response.status_code == 200
    data = response.json()
    assert data["terms"] == ["message", "failing"]
    assert [r["slug"] for r in data["results"]] == [DLQ]
    assert "keeps failing" in data["results"][0]["snippet"]


def test_search_needs_a_query(api):
    assert api.client.get(f"{BASE}/search", headers=api.login()).status_code == 422
    assert api.client.get(f"{BASE}/search", params={"q": ""}, headers=api.login()).status_code == 422


# -- prune --------------------------------------------------------------------------


def test_prune_removes_pages_the_vault_no_longer_has(api):
    api.publish(*two_pages())

    response = api.client.post(f"{BASE}/prune", json={"keep": [IDEMPOTENCY]}, headers=INGEST)

    assert response.status_code == 200
    assert response.json() == {"removed": 1}
    assert api.repository.slugs() == [IDEMPOTENCY]


def test_prune_with_an_empty_keep_list_is_a_422_and_removes_nothing(api):
    api.publish(*two_pages())

    response = api.client.post(f"{BASE}/prune", json={"keep": []}, headers=INGEST)

    assert response.status_code == 422
    assert len(api.repository.slugs()) == 2
