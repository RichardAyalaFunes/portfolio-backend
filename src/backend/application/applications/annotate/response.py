"""Annotate use case -- response DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnnotateResponse:
    added: int
    already_present: int
    unmatched: list[str] = field(default_factory=list)
