"""GetKnowledgeIndex use case -- command DTO (no input)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetKnowledgeIndexCommand:
    pass
