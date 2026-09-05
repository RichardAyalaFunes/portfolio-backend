"""SupabaseSearchRunRepository -- driven adapter implementing ISearchRunRepository."""

from __future__ import annotations

from typing import Any

from postgrest import AsyncPostgrestClient

from backend.application.applications.ports.search_run_repository import ISearchRunRepository

TABLE = "job_search_runs"


class SupabaseSearchRunRepository(ISearchRunRepository):
    def __init__(self, client: AsyncPostgrestClient) -> None:
        self._client = client

    async def list_all(self) -> list[dict[str, Any]]:
        response = await self._client.table(TABLE).select("*").order("run_date", desc=True).execute()
        return list(response.data)

    async def upsert(self, run: dict[str, Any]) -> None:
        await self._client.table(TABLE).upsert(run, on_conflict="run_date").execute()
