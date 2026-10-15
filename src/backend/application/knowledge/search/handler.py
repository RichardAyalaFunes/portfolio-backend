"""SearchKnowledge use case -- handler implementation.

Word-start matching over the whole text of every page: "idemp" finds "idempotency", "race" finds
"race condition" but not "trace". Every term must be present (AND). The database narrows the set;
ranking and the snippet are done here, because they need the text and the matched set is small.

Ranking, most to least: all terms in the title, a term in an alias, a term in a tag, then how often
the terms occur in the body (capped, so a long page does not beat a precise one).
"""

import re
from typing import Any

from backend.application.knowledge.ports.knowledge_repository import IKnowledgeRepository

from .command import SearchKnowledgeCommand
from .port import ISearchKnowledgeUseCase
from .response import SearchKnowledgeResponse

TOKEN_RE = re.compile(r"[\w+#]+", re.UNICODE)
MAX_TERMS = 6
MIN_TERM_LENGTH = 2
TEXT_FETCH_LIMIT = 60
RESULT_LIMIT = 40
SNIPPET_RADIUS = 90
BODY_HIT_CAP = 25


def tokenize(query: str) -> list[str]:
    seen: list[str] = []
    for token in TOKEN_RE.findall(query.lower()):
        if len(token) >= MIN_TERM_LENGTH and token not in seen:
            seen.append(token)
    return seen[:MAX_TERMS]


def _word_start(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term), re.IGNORECASE | re.UNICODE)


def _snippet(text: str, patterns: list[re.Pattern[str]]) -> str:
    first = None
    for pattern in patterns:
        match = pattern.search(text)
        if match and (first is None or match.start() < first.start()):
            first = match
    if first is None:
        return ""
    start = max(0, first.start() - SNIPPET_RADIUS)
    end = min(len(text), first.end() + SNIPPET_RADIUS)
    piece = re.sub(r"\s+", " ", text[start:end]).strip()
    return f"{'…' if start > 0 else ''}{piece}{'…' if end < len(text) else ''}"


class SearchKnowledgeHandler(ISearchKnowledgeUseCase):
    def __init__(self, repository: IKnowledgeRepository) -> None:
        self._repository = repository

    async def execute(self, command: SearchKnowledgeCommand) -> SearchKnowledgeResponse:
        terms = tokenize(command.query)
        if not terms:
            return SearchKnowledgeResponse(query=command.query)

        rows = await self._repository.match(terms)
        patterns = [_word_start(term) for term in terms]

        def in_text(row: dict[str, Any], key: str, pattern: re.Pattern[str]) -> bool:
            value = row.get(key) or ""
            haystack = value if isinstance(value, str) else " ".join(value)
            return bool(pattern.search(haystack))

        def header_score(row: dict[str, Any]) -> int:
            score = 0
            if all(in_text(row, "title", p) for p in patterns):
                score += 100
            elif any(in_text(row, "title", p) for p in patterns):
                score += 30
            if any(in_text(row, "aliases", p) for p in patterns):
                score += 40
            if any(in_text(row, "tags", p) for p in patterns):
                score += 15
            return score

        ranked = sorted(rows, key=lambda r: (-header_score(r), r["title"].lower()))
        texts = await self._repository.search_texts([r["slug"] for r in ranked[:TEXT_FETCH_LIMIT]])

        results: list[dict[str, Any]] = []
        for row in ranked:
            score = header_score(row)
            text = texts.get(row["slug"], "")
            header = "\n".join([row["title"], *row.get("aliases", []), *row.get("tags", [])])
            body = text[len(header) :] if text.startswith(header) else text
            hits = min(BODY_HIT_CAP, sum(len(p.findall(body)) for p in patterns))
            matched_in = (
                "title"
                if any(in_text(row, "title", p) for p in patterns)
                else "alias"
                if any(in_text(row, "aliases", p) for p in patterns)
                else "tag"
                if any(in_text(row, "tags", p) for p in patterns)
                else "text"
            )
            results.append(
                {
                    **{k: v for k, v in row.items() if k not in {"aliases", "tags"}},
                    "score": score + hits,
                    "matched_in": matched_in,
                    "snippet": _snippet(body, patterns) if body else "",
                }
            )
        results.sort(key=lambda r: (-r["score"], r["title"].lower()))
        return SearchKnowledgeResponse(query=command.query, terms=terms, total=len(results), results=results[:RESULT_LIMIT])
