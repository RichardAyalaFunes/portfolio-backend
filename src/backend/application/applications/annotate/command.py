"""Annotate use case -- command DTO. Mirrors annotate.js's {url, note} blocks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnnotateItem:
    url: str
    note: str


@dataclass(frozen=True)
class AnnotateCommand:
    items: list[AnnotateItem]
