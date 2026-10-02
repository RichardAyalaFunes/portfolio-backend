"""PublishRules use case -- response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishRulesResponse:
    published_at: str  # ISO timestamp of this publish
    lanes: int
    lines: int  # search lines, summed over every lane
