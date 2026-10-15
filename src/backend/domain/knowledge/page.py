"""KnowledgePage -- one published note of the dashboard's knowledge library.

The publisher (`.claude/skills/ai-coach/scripts/knowledge/` in the operating-layer repo) converts the
Obsidian notes into JSON documents; this module is the contract those documents must meet before the
backend stores them. The body is block-and-inline JSON that the dashboard renders with React
components, never as HTML, so validation here is what keeps a malformed or hostile document (the
library will also be fed from video transcripts) from reaching the page: unknown block or inline
types, unsafe link schemes, runaway nesting and oversized payloads are rejected with the reason.

Pure Python: no I/O, no framework. See docs/knowledge-library.md for the document shape.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from backend.domain.shared.errors import InvalidValueError

SPACES = ("learn", "reference", "practice")

KINDS = frozenset(
    {
        "topic",
        "concept",
        "decision",
        "catalogue",
        "moc",
        "roadmap",
        "hub",
        "coverage",
        "index",
        "cheat-sheet",
        "quiz",
        "debrief",
        "case",
        "session",
        "guide",
        "note",
    }
)

SLUG_RE = re.compile(r"^(?:learn|reference|practice)(?:/[a-z0-9][a-z0-9-]{0,100}){1,4}$")
SAFE_HREF_RE = re.compile(r"^(?:https?://|mailto:)", re.IGNORECASE)

MAX_BODY_BYTES = 600_000
MAX_SEARCH_TEXT = 100_000
MAX_DEPTH = 8
MAX_NODES = 40_000
MAX_DIAGRAM_ELEMENTS = 400

BLOCK_TYPES = frozenset(
    {"p", "h", "ul", "ol", "table", "code", "quote", "callout", "section", "hr", "diagram", "sits", "ladder", "reveal", "prompt", "score", "terms", "facts"}
)
INLINE_TYPES = frozenset({"b", "i", "s", "code", "a", "br", "ref", "missing"})
CHECKED = frozenset({None, "todo", "done", "partial"})


@dataclass(frozen=True)
class KnowledgePage:
    slug: str
    space: str
    kind: str
    title: str
    group: str
    group_order: int
    order: int
    summary: str
    read_minutes: int
    body: dict[str, Any]
    domain: Optional[str] = None
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    source_path: Optional[str] = None
    source_updated: Optional[str] = None
    content_hash: Optional[str] = None
    search_text: str = field(default="", repr=False)

    @staticmethod
    def from_document(document: Any) -> "KnowledgePage":
        """Validate one document from the publisher; raise InvalidValueError naming the slug and the reason."""
        if not isinstance(document, dict):
            raise InvalidValueError("a page must be a JSON object")
        slug = document.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            raise InvalidValueError(f"slug {slug!r} is not a valid page slug")
        try:
            return _build(slug, document)
        except InvalidValueError as exc:
            raise InvalidValueError(f"{slug}: {exc}") from exc


def _text(document: dict[str, Any], key: str, *, maximum: int, required: bool = True) -> str:
    value = document.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise InvalidValueError(f"{key} must be a non-empty string" if required else f"{key} must be a string")
    if len(value) > maximum:
        raise InvalidValueError(f"{key} is {len(value)} characters, the maximum is {maximum}")
    return value


def _int(document: dict[str, Any], key: str, *, low: int, high: int, default: Optional[int] = None) -> int:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidValueError(f"{key} must be an integer between {low} and {high}")
    return value


def _strings(document: dict[str, Any], key: str, *, items: int, length: int, pattern: Optional[re.Pattern[str]] = None) -> tuple[str, ...]:
    value = document.get(key, [])
    if not isinstance(value, list) or len(value) > items:
        raise InvalidValueError(f"{key} must be a list of at most {items} strings")
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > length:
            raise InvalidValueError(f"{key} must contain non-empty strings of at most {length} characters")
        if pattern is not None and not pattern.match(item):
            raise InvalidValueError(f"{key} contains {item!r}, which is not valid")
    return tuple(value)


def _build(slug: str, document: dict[str, Any]) -> KnowledgePage:
    space = _text(document, "space", maximum=20)
    if space not in SPACES or not slug.startswith(f"{space}/"):
        raise InvalidValueError(f"space {space!r} does not match the slug")
    kind = _text(document, "kind", maximum=30)
    if kind not in KINDS:
        raise InvalidValueError(f"kind {kind!r} is not one of {sorted(KINDS)}")

    body = document.get("body")
    if not isinstance(body, dict):
        raise InvalidValueError("body must be an object with blocks")
    blocks = body.get("blocks")
    if not isinstance(blocks, list):
        raise InvalidValueError("body.blocks must be a list")
    outline = body.get("outline", [])
    related = body.get("related", [])
    if not isinstance(outline, list) or not isinstance(related, list):
        raise InvalidValueError("body.outline and body.related must be lists")
    for entry in outline:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not isinstance(entry.get("text"), str):
            raise InvalidValueError("body.outline entries need an id and a text")
    for entry in related:
        if not isinstance(entry, dict) or not isinstance(entry.get("slug"), str) or not SLUG_RE.match(entry["slug"]):
            raise InvalidValueError("body.related entries need a valid slug")

    try:
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvalidValueError(f"body must be plain JSON: {exc}") from exc
    if len(encoded) > MAX_BODY_BYTES:
        raise InvalidValueError(f"body is {len(encoded)} bytes serialised, the maximum is {MAX_BODY_BYTES}")
    _Budget().blocks(blocks, depth=0)

    updated = document.get("source_updated")
    if updated is not None:
        try:
            date.fromisoformat(str(updated))
        except ValueError as exc:
            raise InvalidValueError("source_updated must be an ISO date") from exc

    domain = document.get("domain")
    if domain is not None and (not isinstance(domain, str) or len(domain) > 60):
        raise InvalidValueError("domain must be a string of at most 60 characters")

    return KnowledgePage(
        slug=slug,
        space=space,
        kind=kind,
        title=_text(document, "title", maximum=300),
        group=_text(document, "group", maximum=120, required=False),
        group_order=_int(document, "group_order", low=0, high=100_000, default=0),
        order=_int(document, "order", low=0, high=10_000_000, default=0),
        summary=_text(document, "summary", maximum=600, required=False),
        read_minutes=_int(document, "read_minutes", low=1, high=240, default=1),
        body=body,
        domain=domain,
        tags=_strings(document, "tags", items=60, length=120),
        aliases=_strings(document, "aliases", items=60, length=160),
        links=_strings(document, "links", items=500, length=220, pattern=SLUG_RE),
        source_path=_text(document, "source_path", maximum=400, required=False) or None,
        source_updated=str(updated) if updated is not None else None,
        content_hash=_text(document, "content_hash", maximum=128, required=False) or None,
        search_text=_text(document, "search_text", maximum=MAX_SEARCH_TEXT, required=False),
    )


class _Budget:
    """Walks a body once, enforcing the allowed node types, nesting depth and total size."""

    def __init__(self) -> None:
        self.nodes = 0

    def _count(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise InvalidValueError(f"body has more than {MAX_NODES} nodes")
        if depth > MAX_DEPTH:
            raise InvalidValueError(f"body nests deeper than {MAX_DEPTH} levels")

    def blocks(self, blocks: Any, depth: int) -> None:
        if not isinstance(blocks, list):
            raise InvalidValueError("a block list must be a list")
        for block in blocks:
            self.block(block, depth)

    def inline(self, inline: Any, depth: int) -> None:
        if not isinstance(inline, list):
            raise InvalidValueError("inline content must be a list")
        for node in inline:
            self._count(depth)
            if isinstance(node, str):
                continue
            if not isinstance(node, dict) or node.get("t") not in INLINE_TYPES:
                raise InvalidValueError(f"unknown inline node {node!r}"[:160])
            kind = node["t"]
            if kind == "code" and not isinstance(node.get("v"), str):
                raise InvalidValueError("a code span needs a string value")
            if kind == "a":
                href = node.get("href")
                if not isinstance(href, str) or not SAFE_HREF_RE.match(href) or len(href) > 2000:
                    raise InvalidValueError("a link must be an http(s) or mailto address")
            if kind == "ref" and not (isinstance(node.get("slug"), str) and SLUG_RE.match(node["slug"])):
                raise InvalidValueError("a reference needs a valid slug")
            if kind in {"b", "i", "s", "a", "ref", "missing"}:
                self.inline(node.get("c", []), depth + 1)

    def block(self, block: Any, depth: int) -> None:
        self._count(depth)
        if not isinstance(block, dict) or block.get("t") not in BLOCK_TYPES:
            raise InvalidValueError(f"unknown block {block!r}"[:160])
        t = block["t"]
        if t in {"p", "h"}:
            self.inline(block.get("c"), depth)
            if t == "h" and (isinstance(block.get("level"), bool) or not isinstance(block.get("level"), int) or not 1 <= block["level"] <= 6):
                raise InvalidValueError("a heading level must be 1 to 6")
        elif t in {"ul", "ol"}:
            items = block.get("items")
            if not isinstance(items, list):
                raise InvalidValueError("a list needs items")
            for item in items:
                if not isinstance(item, dict):
                    raise InvalidValueError("a list item must be an object")
                if item.get("checked") not in CHECKED:
                    raise InvalidValueError("a list item's checked state is not valid")
                self.inline(item.get("c"), depth + 1)
                self.blocks(item.get("children", []), depth + 1)
        elif t == "table":
            head, rows = block.get("head"), block.get("rows")
            if not isinstance(head, list) or not isinstance(rows, list):
                raise InvalidValueError("a table needs head and rows")
            for cell in head:
                self.inline(cell, depth + 1)
            for row in rows:
                if not isinstance(row, list):
                    raise InvalidValueError("a table row must be a list")
                for cell in row:
                    self.inline(cell, depth + 1)
            marks = block.get("marks")
            if marks is not None and (isinstance(marks, bool) or not isinstance(marks, int) or not 0 <= marks < len(head)):
                raise InvalidValueError("a table's marks column is out of range")
        elif t == "code":
            if not isinstance(block.get("text"), str):
                raise InvalidValueError("a code block needs text")
        elif t == "prompt":
            if not isinstance(block.get("text"), str):
                raise InvalidValueError("a prompt block needs text")
        elif t in {"quote", "callout", "section", "reveal"}:
            for key in ("title", "tone", "variant", "hint"):
                if block.get(key) is not None and not isinstance(block.get(key), str):
                    raise InvalidValueError(f"{t}.{key} must be a string")
            self.blocks(block.get("c"), depth + 1)
        elif t == "sits":
            for row in _list(block, "rows"):
                if not isinstance(row, dict) or not isinstance(row.get("label"), str):
                    raise InvalidValueError("a sits row needs a label")
                self.inline(row.get("c"), depth + 1)
        elif t == "ladder":
            for item in _list(block, "items"):
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise InvalidValueError("a ladder item needs an id")
                self.inline(item.get("q"), depth + 1)
                self.inline(item.get("a"), depth + 1)
        elif t == "score":
            for key in ("strong", "fail"):
                for entry in _list(block, key):
                    self.inline(entry, depth + 1)
            if block.get("other") is not None:
                self.block(block["other"], depth + 1)
        elif t == "terms":
            for entry in _list(block, "items"):
                self.inline(entry, depth + 1)
        elif t == "facts":
            for entry in _list(block, "items"):
                if not isinstance(entry, dict) or not isinstance(entry.get("k"), str):
                    raise InvalidValueError("a fact needs a key")
                self.inline(entry.get("c"), depth + 1)
        elif t == "diagram":
            self._diagram(block)

    def _diagram(self, block: dict[str, Any]) -> None:
        kind = block.get("kind")
        if kind not in {"flow", "sequence"}:
            raise InvalidValueError("a diagram is a flow or a sequence")
        for key in ("w", "h"):
            if not _finite(block.get(key)) or not 0 < block[key] < 20_000:
                raise InvalidValueError(f"diagram.{key} must be a positive number")
        if kind == "flow":
            nodes, edges = _list(block, "nodes"), _list(block, "edges")
            if len(nodes) + len(edges) > MAX_DIAGRAM_ELEMENTS:
                raise InvalidValueError("a diagram has too many elements")
            for node in nodes:
                if not isinstance(node, dict) or not isinstance(node.get("id"), str):
                    raise InvalidValueError("a diagram node needs an id")
                for key in ("x", "y", "w", "h"):
                    if not _finite(node.get(key)):
                        raise InvalidValueError(f"diagram node.{key} must be a number")
                if not isinstance(node.get("lines"), list) or not all(isinstance(line, str) for line in node["lines"]):
                    raise InvalidValueError("diagram node.lines must be strings")
            for edge in edges:
                points = edge.get("pts") if isinstance(edge, dict) else None
                if not isinstance(points, list) or len(points) < 2 or not all(
                    isinstance(p, list) and len(p) == 2 and _finite(p[0]) and _finite(p[1]) for p in points
                ):
                    raise InvalidValueError("a diagram edge needs at least two [x, y] points")
        else:
            participants, steps = _list(block, "participants"), _list(block, "steps")
            if len(participants) + len(steps) > MAX_DIAGRAM_ELEMENTS:
                raise InvalidValueError("a diagram has too many elements")
            for participant in participants:
                if not isinstance(participant, dict) or not _finite(participant.get("x")):
                    raise InvalidValueError("a sequence participant needs an x position")
            for step in steps:
                if not isinstance(step, dict) or step.get("type") not in {"message", "note"} or not _finite(step.get("y")):
                    raise InvalidValueError("a sequence step needs a type and a y position")


def _list(block: dict[str, Any], key: str) -> list[Any]:
    value = block.get(key)
    if not isinstance(value, list):
        raise InvalidValueError(f"{block.get('t')}.{key} must be a list")
    return value


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
