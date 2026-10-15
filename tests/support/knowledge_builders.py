"""Builders for knowledge-library documents, shaped exactly like the publisher's output."""

from __future__ import annotations

import copy
from typing import Any


def text_block(text: str) -> dict[str, Any]:
    return {"t": "p", "c": [text]}


def make_document(slug: str = "reference/backend/idempotency", **overrides: Any) -> dict[str, Any]:
    """A valid published document. Keyword overrides replace top-level fields."""
    space = slug.split("/", 1)[0]
    title = overrides.pop("title", "Idempotency")
    document: dict[str, Any] = {
        "slug": slug,
        "space": space,
        "kind": "concept",
        "title": title,
        "group": "Backend",
        "group_order": 1,
        "order": 1,
        "domain": "backend",
        "summary": "Doing it twice has the effect of doing it once.",
        "read_minutes": 3,
        "tags": ["reliability", "retries"],
        "aliases": ["idempotency key", "idempotent"],
        "links": [],
        "source_path": "_AI_Knowledge/Backend/idempotency.md",
        "source_updated": "2026-09-30",
        "content_hash": "a" * 64,
        "body": {
            "blocks": [
                {"t": "callout", "tone": "lead", "title": "In one line", "c": [text_block("Doing it twice is safe.")]},
                {"t": "h", "level": 2, "id": "why-it-exists", "c": ["Why it exists"]},
                text_block("Retries happen, so the same request can arrive twice."),
            ],
            "outline": [{"id": "why-it-exists", "text": "Why it exists", "level": 2}],
            "related": [],
        },
        "search_text": f"{title}\nidempotency key\nidempotent\nreliability\nretries\nRetries happen, so the same request can arrive twice.",
    }
    document.update(copy.deepcopy(overrides))
    return document
