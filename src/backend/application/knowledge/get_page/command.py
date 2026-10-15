"""GetKnowledgePage use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetKnowledgePageCommand:
    slug: str
