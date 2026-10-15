"""IKnowledgeRepository -- driven port for the dashboard's knowledge library (table knowledge_pages).

Rows travel as plain dicts. "Summary" rows carry the fields the library index and a search result
need (slug, space, kind, title, group, group_order, order, domain, summary, read_minutes, tags,
aliases, source_updated) and never the body or the search text, which are large.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.domain.knowledge.page import KnowledgePage


class IKnowledgeRepository(ABC):
    @abstractmethod
    async def upsert(self, pages: list[KnowledgePage]) -> None:
        """Insert or replace each page by slug."""

    @abstractmethod
    async def list_summaries(self) -> list[dict[str, Any]]:
        """Every page's summary row, in library order (space, group_order, group, order, title)."""

    @abstractmethod
    async def get(self, slug: str) -> Optional[dict[str, Any]]:
        """The summary row plus `body` and `links`, or None."""

    @abstractmethod
    async def backlinks(self, slug: str) -> list[dict[str, Any]]:
        """Summary rows of the pages whose `links` contain `slug`, in library order."""

    @abstractmethod
    async def list_slugs(self) -> list[str]: ...

    @abstractmethod
    async def delete(self, slugs: list[str]) -> None: ...

    @abstractmethod
    async def match(self, terms: list[str]) -> list[dict[str, Any]]:
        """Summary rows of the pages whose text contains every term as the start of a word
        (case-insensitive). Title, aliases and tags are part of that text."""

    @abstractmethod
    async def search_texts(self, slugs: list[str]) -> dict[str, str]:
        """slug -> the page's plain text, for the given slugs."""
