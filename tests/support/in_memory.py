"""In-memory fakes of the driven ports. Shared by the unit and route tests and by
scripts/dev_fake_server.py. Nothing here touches the network or a database.

InMemoryApplicationRepository stores rows (plain dicts), not entities, and converts
through the real Supabase mappers on every read and write. That keeps it honest about
what a database round trip does to a JobApplication: ISO strings become dates, JSON
columns are copied, enums are validated, `created_at` / `updated_at` are stamped by
the "database", and a column the mappers forget to carry simply disappears.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Optional

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository
from backend.domain.knowledge.page import KnowledgePage
from backend.application.applications.ports.search_rules_repository import ISearchRulesRepository
from backend.application.applications.ports.search_run_repository import ISearchRunRepository
from backend.application.auth.ports.login_attempt_repository import ILoginAttemptRepository
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId
from backend.infrastructure.adapters.driven.supabase.mappers import entity_to_row, row_to_entity


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sort_rows(rows: list[dict[str, Any]], sort: Optional[str]) -> list[dict[str, Any]]:
    """`column.asc|desc`, default `posted_date.desc`, like the Supabase repository.
    PostgreSQL sorts NULL as the largest value: last ascending, first descending."""
    column, _, direction = (sort or "posted_date.desc").partition(".")
    descending = direction == "desc"
    if rows and column not in rows[0]:
        raise ValueError(f"unknown sort column {column!r}")
    present = sorted((r for r in rows if r[column] is not None), key=lambda r: r[column], reverse=descending)
    missing = [r for r in rows if r[column] is None]
    return missing + present if descending else present + missing


class InMemoryApplicationRepository(IJobApplicationRepository):
    def __init__(self, applications: Optional[Iterable[JobApplication]] = None) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        if applications:
            self.add(*applications)

    # -- synchronous helpers for seeding and asserting -------------------------

    def add(self, *applications: JobApplication) -> None:
        """Seed rows directly. Keeps any created_at / updated_at the entity carries."""
        now = _now()
        for application in applications:
            row = copy.deepcopy(entity_to_row(application))
            row["created_at"] = row.get("created_at") or now
            row["updated_at"] = row.get("updated_at") or now
            self._rows[row["id"]] = row

    def all(self) -> list[JobApplication]:
        """Every stored role, archived included, in insertion order."""
        return [row_to_entity(copy.deepcopy(row)) for row in self._rows.values()]

    def by_id(self, application_id: str) -> JobApplication:
        return row_to_entity(copy.deepcopy(self._rows[str(application_id)]))

    # -- IJobApplicationRepository ---------------------------------------------

    async def list(
        self,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        group: Optional[str] = None,
        source: Optional[str] = None,
        live_state: Optional[str] = None,
        run_date: Optional[str] = None,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[JobApplication]:
        rows = [row for row in self._rows.values() if include_archived or row["archived_at"] is None]
        for column, wanted in (
            ("status", status),
            ("application_stage", stage),
            ("group", group),
            ("source", source),
            ("live_state", live_state),
            ("run_date", run_date),
        ):
            if wanted:
                rows = [row for row in rows if row[column] == wanted]
        if query:
            needle = query.lower()
            rows = [row for row in rows if needle in row["title"].lower() or needle in row["company"].lower()]
        return [row_to_entity(copy.deepcopy(row)) for row in _sort_rows(rows, sort)]

    async def get(self, application_id: ApplicationId) -> Optional[JobApplication]:
        row = self._rows.get(str(application_id))
        return row_to_entity(copy.deepcopy(row)) if row else None

    async def get_by_identity_key(self, identity_key: str) -> Optional[JobApplication]:
        row = next((r for r in self._rows.values() if r["identity_key"] == identity_key), None)
        return row_to_entity(copy.deepcopy(row)) if row else None

    async def create(self, application: JobApplication) -> JobApplication:
        row = copy.deepcopy(entity_to_row(application))
        if any(stored["identity_key"] == row["identity_key"] for stored in self._rows.values()):
            raise ValueError(f"duplicate identity_key {row['identity_key']!r}")  # unique in the real table
        row["created_at"] = row["updated_at"] = _now()  # NOT NULL DEFAULT now()
        self._rows[row["id"]] = row
        return row_to_entity(copy.deepcopy(row))

    async def update(self, application: JobApplication) -> JobApplication:
        key = str(application.id)
        stored = self._rows.get(key)
        if stored is None:
            raise LookupError(f"no job_applications row {key}")
        row = copy.deepcopy(entity_to_row(application))
        row["created_at"] = stored["created_at"]  # the real update() never writes it
        row["updated_at"] = _now()  # trg_job_applications_updated_at
        self._rows[key] = row
        return row_to_entity(copy.deepcopy(row))

    async def save_skill_match(self, application: JobApplication) -> None:
        key = str(application.id)
        stored = self._rows.get(key)
        if stored is None:
            raise LookupError(f"no job_applications row {key}")
        # Only this column travels, like the real PATCH; every other column stays as stored.
        stored["skill_match"] = copy.deepcopy(entity_to_row(application)["skill_match"])
        stored["updated_at"] = _now()


class InMemoryRunRepository(ISearchRunRepository):
    def __init__(self, runs: Optional[Iterable[dict[str, Any]]] = None) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        for run in runs or []:
            self._runs[str(run["run_date"])] = copy.deepcopy(run)

    async def list_all(self) -> list[dict[str, Any]]:
        """Newest run first, like the real `order run_date desc`."""
        return [copy.deepcopy(self._runs[key]) for key in sorted(self._runs, reverse=True)]

    async def upsert(self, run: dict[str, Any]) -> None:
        self._runs[str(run["run_date"])] = copy.deepcopy(run)


class InMemoryRulesRepository(ISearchRulesRepository):
    """The singleton job_search_rules row."""

    def __init__(self) -> None:
        self._stored: Optional[dict[str, Any]] = None

    async def get(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._stored)

    async def publish(self, content: dict[str, Any]) -> str:
        published_at = _now()
        self._stored = {"content": copy.deepcopy(content), "published_at": published_at}
        return published_at

    # -- synchronous helpers for seeding and asserting -------------------------

    def seed(self, content: dict[str, Any], published_at: Optional[str] = None) -> None:
        self._stored = {"content": copy.deepcopy(content), "published_at": published_at or _now()}

    def peek(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._stored)


class InMemoryKnowledgeRepository(IKnowledgeRepository):
    """The knowledge_pages table. Rows are stored the way the Supabase adapter writes them (summary
    fields, `links`, `body`, `search_text`), so a field the adapter forgets to carry disappears here
    too, and `match` uses the same word-start rule as the database regex."""

    def __init__(self, pages: Optional[Iterable[KnowledgePage]] = None) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        for page in pages or []:
            self._store(page)

    def _store(self, page: KnowledgePage) -> None:
        self._rows[page.slug] = copy.deepcopy(
            {
                "slug": page.slug,
                "space": page.space,
                "kind": page.kind,
                "title": page.title,
                "group": page.group,
                "group_order": page.group_order,
                "order": page.order,
                "domain": page.domain,
                "summary": page.summary,
                "read_minutes": page.read_minutes,
                "tags": list(page.tags),
                "aliases": list(page.aliases),
                "source_updated": page.source_updated,
                "links": list(page.links),
                "body": page.body,
                "source_path": page.source_path,
                "content_hash": page.content_hash,
                "published_at": _now(),
                "search_text": page.search_text,
            }
        )

    @staticmethod
    def _summary(row: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "slug", "space", "kind", "title", "group", "group_order", "order", "domain",
            "summary", "read_minutes", "tags", "aliases", "source_updated",
        )  # fmt: skip
        return copy.deepcopy({key: row[key] for key in keys})

    def _ordered(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda r: (r["space"], r["group_order"], r["group"], r["order"], r["title"]))

    # -- synchronous helpers for seeding and asserting -------------------------

    def slugs(self) -> list[str]:
        return sorted(self._rows)

    def row(self, slug: str) -> dict[str, Any]:
        return copy.deepcopy(self._rows[slug])

    # -- IKnowledgeRepository ---------------------------------------------------

    async def upsert(self, pages: list[KnowledgePage]) -> None:
        for page in pages:
            self._store(page)

    async def list_summaries(self) -> list[dict[str, Any]]:
        return [self._summary(row) for row in self._ordered(self._rows.values())]

    async def get(self, slug: str) -> Optional[dict[str, Any]]:
        row = self._rows.get(slug)
        if row is None:
            return None
        detail = self._summary(row)
        detail.update(
            copy.deepcopy({key: row[key] for key in ("links", "body", "source_path", "content_hash", "published_at")})
        )
        return detail

    async def backlinks(self, slug: str) -> list[dict[str, Any]]:
        rows = [row for row in self._rows.values() if slug in row["links"] and row["slug"] != slug]
        return [self._summary(row) for row in self._ordered(rows)]

    async def list_slugs(self) -> list[str]:
        return list(self._rows)

    async def delete(self, slugs: list[str]) -> None:
        for slug in slugs:
            self._rows.pop(slug, None)

    async def match(self, terms: list[str]) -> list[dict[str, Any]]:
        patterns = [re.compile(r"(?<!\w)" + re.escape(term), re.IGNORECASE) for term in terms]
        rows = [row for row in self._rows.values() if all(p.search(row["search_text"]) for p in patterns)]
        return [self._summary(row) for row in self._ordered(rows)]

    async def search_texts(self, slugs: list[str]) -> dict[str, str]:
        return {slug: self._rows[slug]["search_text"] for slug in slugs if slug in self._rows}


class InMemoryLoginAttemptRepository(ILoginAttemptRepository):
    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []

    async def record(self, *, ip: Optional[str], device_id: str, success: bool) -> None:
        self.attempts.append(
            {"ip": ip, "device_id": device_id, "success": success, "at": datetime.now(tz=timezone.utc)}
        )

    async def count_recent_failures(self, *, ip: Optional[str], device_id: str, since: datetime) -> int:
        # Like the Supabase adapter: a missing ip falls back to matching the device only.
        return sum(
            1
            for attempt in self.attempts
            if not attempt["success"]
            and attempt["at"] >= since
            and (attempt["device_id"] == device_id or (ip is not None and attempt["ip"] == ip))
        )
