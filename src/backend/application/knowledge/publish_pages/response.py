"""PublishKnowledgePages use case -- response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishKnowledgePagesResponse:
    upserted: int
