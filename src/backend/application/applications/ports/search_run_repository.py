"""ISearchRunRepository -- driven port for job_search_runs persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ISearchRunRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def upsert(self, run: dict[str, Any]) -> None:
        """Insert or replace by run_date (primary key)."""
