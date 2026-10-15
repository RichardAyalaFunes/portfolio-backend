"""SearchKnowledge use case -- response DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchKnowledgeResponse:
    query: str
    terms: list[str] = field(default_factory=list)
    total: int = 0  # pages that matched; `results` is capped
    # summary fields plus score, matched_in ("title" | "alias" | "tag" | "text") and snippet
    results: list[dict[str, Any]] = field(default_factory=list)
