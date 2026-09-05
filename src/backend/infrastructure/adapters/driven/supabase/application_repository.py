"""SupabaseJobApplicationRepository -- driven adapter implementing IJobApplicationRepository
over PostgREST (via postgrest-py), using the service-role key server-side only."""

from __future__ import annotations

from typing import Optional

from postgrest import AsyncPostgrestClient

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId

from .mappers import entity_to_row, row_to_entity

TABLE = "job_applications"


class SupabaseJobApplicationRepository(IJobApplicationRepository):
    def __init__(self, client: AsyncPostgrestClient) -> None:
        self._client = client

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
        builder = self._client.table(TABLE).select("*")
        if not include_archived:
            builder = builder.is_("archived_at", "null")
        if status:
            builder = builder.eq("status", status)
        if stage:
            builder = builder.eq("application_stage", stage)
        if group:
            builder = builder.eq("group", group)
        if source:
            builder = builder.eq("source", source)
        if live_state:
            builder = builder.eq("live_state", live_state)
        if run_date:
            builder = builder.eq("run_date", run_date)
        if query:
            builder = builder.or_(f"title.ilike.%{query}%,company.ilike.%{query}%")

        sort_column, _, sort_dir = (sort or "posted_date.desc").partition(".")
        builder = builder.order(sort_column, desc=(sort_dir == "desc"))

        response = await builder.execute()
        return [row_to_entity(row) for row in response.data]

    async def get(self, application_id: ApplicationId) -> Optional[JobApplication]:
        response = (
            await self._client.table(TABLE).select("*").eq("id", str(application_id)).maybe_single().execute()
        )
        return row_to_entity(response.data) if response and response.data else None

    async def get_by_identity_key(self, identity_key: str) -> Optional[JobApplication]:
        response = (
            await self._client.table(TABLE)
            .select("*")
            .eq("identity_key", identity_key)
            .maybe_single()
            .execute()
        )
        return row_to_entity(response.data) if response and response.data else None

    async def create(self, application: JobApplication) -> JobApplication:
        row = entity_to_row(application)
        # created_at/updated_at are NOT NULL DEFAULT now() -- omit so the DB default
        # applies; sending an explicit null would violate the constraint.
        row.pop("created_at", None)
        row.pop("updated_at", None)
        response = await self._client.table(TABLE).insert(row).execute()
        return row_to_entity(response.data[0])

    async def update(self, application: JobApplication) -> JobApplication:
        row = entity_to_row(application)
        row.pop("id", None)
        row.pop("created_at", None)
        row.pop("updated_at", None)  # trg_job_applications_updated_at sets this on every UPDATE
        response = (
            await self._client.table(TABLE).update(row).eq("id", str(application.id)).execute()
        )
        return row_to_entity(response.data[0])
