"""PruneKnowledgePages use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PruneKnowledgePagesCommand:
    keep: list[str]
