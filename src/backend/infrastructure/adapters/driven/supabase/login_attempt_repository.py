"""SupabaseLoginAttemptRepository -- driven adapter implementing ILoginAttemptRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from postgrest import AsyncPostgrestClient

from backend.application.auth.ports.login_attempt_repository import ILoginAttemptRepository

TABLE = "dashboard_login_attempts"


class SupabaseLoginAttemptRepository(ILoginAttemptRepository):
    def __init__(self, client: AsyncPostgrestClient) -> None:
        self._client = client

    async def record(self, *, ip: Optional[str], device_id: str, success: bool) -> None:
        await self._client.table(TABLE).insert(
            {"ip": ip, "device_id": device_id, "success": success}
        ).execute()

    async def count_recent_failures(self, *, ip: Optional[str], device_id: str, since: datetime) -> int:
        builder = (
            self._client.table(TABLE)
            .select("id", count="exact")
            .eq("success", False)
            .gte("attempted_at", since.isoformat())
        )
        builder = builder.or_(f"device_id.eq.{device_id},ip.eq.{ip}") if ip else builder.eq("device_id", device_id)
        response = await builder.execute()
        return response.count or 0
