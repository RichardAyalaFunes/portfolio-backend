"""SearchKnowledge use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchKnowledgeCommand:
    query: str
