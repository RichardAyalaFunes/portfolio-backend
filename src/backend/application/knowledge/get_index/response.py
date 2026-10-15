"""GetKnowledgeIndex use case -- response DTO."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GetKnowledgeIndexResponse:
    pages: list[dict[str, Any]]  # summary rows, in library order
