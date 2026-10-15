"""GetKnowledgePage use case -- response DTO."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GetKnowledgePageResponse:
    page: dict[str, Any]  # summary fields plus body and links
    backlinks: list[dict[str, Any]]  # summary rows of the pages that link to this one
