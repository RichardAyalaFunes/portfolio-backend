"""ILoginAttemptRepository -- driven port for dashboard_login_attempts persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class ILoginAttemptRepository(ABC):
    @abstractmethod
    async def record(self, *, ip: Optional[str], device_id: str, success: bool) -> None:
        ...

    @abstractmethod
    async def count_recent_failures(
        self, *, ip: Optional[str], device_id: str, since: datetime
    ) -> int:
        """Count failed attempts at or after `since`, matching EITHER ip OR device_id
        (either signal being over the limit is enough to lock, per the approved design)."""
