"""PruneKnowledgePages use case -- response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PruneKnowledgePagesResponse:
    removed: int
