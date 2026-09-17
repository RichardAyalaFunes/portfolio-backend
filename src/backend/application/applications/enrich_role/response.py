"""EnrichRole use case -- response DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnrichRoleResponse:
    matched: int
    updated: int
    unmatched: list[str] = field(default_factory=list)
