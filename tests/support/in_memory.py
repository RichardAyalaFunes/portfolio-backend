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
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Optional

from backend.application.applications.ports.application_repository import IJobApplicationRepository
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
