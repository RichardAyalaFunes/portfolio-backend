"""PublishKnowledgePages use case -- command DTO.

`pages` are the documents exactly as the publisher sends them; the handler validates each one
(domain.knowledge.page) before anything is written.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublishKnowledgePagesCommand:
    pages: list[Any]
