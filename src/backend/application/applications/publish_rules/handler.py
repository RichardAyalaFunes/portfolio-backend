"""PublishRules use case -- handler implementation.

The job-search agent is a private CLI whose config decides how it searches and
scores; this use case lets it publish a copy of those rules so the dashboard can
show Richard what the agent is actually doing. Publishing replaces the previous
document (singleton row).

Validation is a sanity check, not a schema: the document is opaque JSON, and only
the keys the dashboard cannot render without are enforced. Anything beyond them is
stored as sent, so the agent can grow its document without a backend release.
"""

import json
from typing import Any

from backend.application.applications.ports.search_rules_repository import ISearchRulesRepository
from backend.domain.shared.errors import InvalidValueError

from .command import PublishRulesCommand
from .port import IPublishRulesUseCase
from .response import PublishRulesResponse

MAX_CONTENT_BYTES = 400_000


def validate_rules(content: Any) -> tuple[int, int]:
    """Raise InvalidValueError unless `content` is a usable rules document; return
    (lane count, total search-line count)."""
    if not isinstance(content, dict):
        raise InvalidValueError("rules must be a JSON object")

    version = content.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise InvalidValueError("schema_version must be an integer")

    lanes = content.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise InvalidValueError("lanes must be a non-empty list")

    lines = 0
    for index, lane in enumerate(lanes):
        where = f"lanes[{index}]"
        if not isinstance(lane, dict):
            raise InvalidValueError(f"{where} must be an object")
        for key in ("id", "label"):
            value = lane.get(key)
            if not isinstance(value, str) or not value.strip():
                raise InvalidValueError(f"{where}.{key} must be a non-empty string")
        if not isinstance(lane.get("lines"), list):
            raise InvalidValueError(f"{where}.lines must be a list")
        lines += len(lane["lines"])

    try:
        size = len(json.dumps(content, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise InvalidValueError(f"rules must be plain JSON: {exc}") from exc
    if size > MAX_CONTENT_BYTES:
        raise InvalidValueError(f"rules are {size} bytes serialised, the maximum is {MAX_CONTENT_BYTES}")

    return len(lanes), lines


class PublishRulesHandler(IPublishRulesUseCase):
    def __init__(self, repository: ISearchRulesRepository) -> None:
        self._repository = repository

    async def execute(self, command: PublishRulesCommand) -> PublishRulesResponse:
        lanes, lines = validate_rules(command.content)
        published_at = await self._repository.publish(command.content)
        return PublishRulesResponse(published_at=published_at, lanes=lanes, lines=lines)
