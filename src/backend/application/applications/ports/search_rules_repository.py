"""ISearchRulesRepository -- driven port for the job_search_rules singleton row."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class ISearchRulesRepository(ABC):
    @abstractmethod
    async def get(self) -> Optional[dict[str, Any]]:
        """The published document as {"content": dict, "published_at": str (ISO)},
        or None when nothing has been published yet."""

    @abstractmethod
    async def publish(self, content: dict[str, Any]) -> str:
        """Insert or replace the single document (row id = 1) and return its
        `published_at` as an ISO timestamp string."""
