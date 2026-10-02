"""SupabaseSearchRulesRepository -- driven adapter implementing ISearchRulesRepository
over the singleton job_search_rules row (id = 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from postgrest import AsyncPostgrestClient

from backend.application.applications.ports.search_rules_repository import ISearchRulesRepository

TABLE = "job_search_rules"
SINGLETON_ID = 1


class SupabaseSearchRulesRepository(ISearchRulesRepository):
    def __init__(self, client: AsyncPostgrestClient) -> None:
        self._client = client

    async def get(self) -> Optional[dict[str, Any]]:
        response = (
            await self._client.table(TABLE)
            .select("content,published_at")
            .eq("id", SINGLETON_ID)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        row = response.data[0]
        return {"content": row["content"], "published_at": str(row["published_at"])}

    async def publish(self, content: dict[str, Any]) -> str:
        published_at = datetime.now(tz=timezone.utc).isoformat()
        await self._client.table(TABLE).upsert(
            {"id": SINGLETON_ID, "content": content, "published_at": published_at},
            on_conflict="id",
        ).execute()
        return published_at
