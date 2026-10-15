"""SupabaseKnowledgeRepository -- driven adapter implementing IKnowledgeRepository over the
knowledge_pages table (PostgREST, service-role key, server-side only)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from postgrest import AsyncPostgrestClient, ReturnMethod

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository
from backend.domain.knowledge.page import KnowledgePage

TABLE = "knowledge_pages"
SUMMARY_COLUMNS = (
    "slug,space,kind,title,group_label,group_order,sort_order,domain,summary,read_minutes,tags,aliases,source_updated"
)
DETAIL_COLUMNS = f"{SUMMARY_COLUMNS},links,body,source_path,content_hash,published_at"


def page_to_row(page: KnowledgePage, published_at: str) -> dict[str, Any]:
    return {
        "slug": page.slug,
        "space": page.space,
        "kind": page.kind,
        "title": page.title,
        "group_label": page.group,
        "group_order": page.group_order,
        "sort_order": page.order,
        "domain": page.domain,
        "summary": page.summary,
        "read_minutes": page.read_minutes,
        "tags": list(page.tags),
        "aliases": list(page.aliases),
        "links": list(page.links),
        "source_path": page.source_path,
        "source_updated": page.source_updated,
        "content_hash": page.content_hash,
        "body": page.body,
        "search_text": page.search_text,
        "published_at": published_at,
    }


def row_to_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "space": row["space"],
        "kind": row["kind"],
        "title": row["title"],
        "group": row.get("group_label") or "",
        "group_order": row.get("group_order") or 0,
        "order": row.get("sort_order") or 0,
        "domain": row.get("domain"),
        "summary": row.get("summary") or "",
        "read_minutes": row.get("read_minutes") or 1,
        "tags": row.get("tags") or [],
        "aliases": row.get("aliases") or [],
        "source_updated": str(row["source_updated"]) if row.get("source_updated") else None,
    }


def _ordered(builder: Any) -> Any:
    return (
        builder.order("space")
        .order("group_order")
        .order("group_label")
        .order("sort_order")
        .order("title")
    )


def _word_start_pattern(term: str) -> str:
    """A PostgreSQL regex that matches `term` at the start of a word (`\\m`)."""
    return "\\m" + re.sub(r"([^0-9A-Za-z_])", r"\\\1", term)


class SupabaseKnowledgeRepository(IKnowledgeRepository):
    def __init__(self, client: AsyncPostgrestClient) -> None:
        self._client = client

    async def upsert(self, pages: list[KnowledgePage]) -> None:
        if not pages:
            return
        published_at = datetime.now(tz=timezone.utc).isoformat()
        rows = [page_to_row(page, published_at) for page in pages]
        # return=minimal: the rows carry whole bodies, and the caller only needs to know it worked
        await self._client.table(TABLE).upsert(rows, on_conflict="slug", returning=ReturnMethod.minimal).execute()

    async def list_summaries(self) -> list[dict[str, Any]]:
        response = await _ordered(self._client.table(TABLE).select(SUMMARY_COLUMNS)).execute()
        return [row_to_summary(row) for row in response.data]

    async def get(self, slug: str) -> Optional[dict[str, Any]]:
        response = await self._client.table(TABLE).select(DETAIL_COLUMNS).eq("slug", slug).limit(1).execute()
        if not response.data:
            return None
        row = response.data[0]
        return {
            **row_to_summary(row),
            "links": row.get("links") or [],
            "body": row["body"],
            "source_path": row.get("source_path"),
            "content_hash": row.get("content_hash"),
            "published_at": str(row.get("published_at")) if row.get("published_at") else None,
        }

    async def backlinks(self, slug: str) -> list[dict[str, Any]]:
        builder = self._client.table(TABLE).select(SUMMARY_COLUMNS).contains("links", [slug])
        response = await _ordered(builder).execute()
        return [row_to_summary(row) for row in response.data if row["slug"] != slug]

    async def list_slugs(self) -> list[str]:
        response = await self._client.table(TABLE).select("slug").execute()
        return [row["slug"] for row in response.data]

    async def delete(self, slugs: list[str]) -> None:
        if not slugs:
            return
        await self._client.table(TABLE).delete(returning=ReturnMethod.minimal).in_("slug", slugs).execute()

    async def match(self, terms: list[str]) -> list[dict[str, Any]]:
        builder = self._client.table(TABLE).select(SUMMARY_COLUMNS)
        for term in terms:
            builder = builder.filter("search_text", "imatch", _word_start_pattern(term))
        response = await _ordered(builder).execute()
        return [row_to_summary(row) for row in response.data]

    async def search_texts(self, slugs: list[str]) -> dict[str, str]:
        if not slugs:
            return {}
        response = await self._client.table(TABLE).select("slug,search_text").in_("slug", slugs).execute()
        return {row["slug"]: row.get("search_text") or "" for row in response.data}
