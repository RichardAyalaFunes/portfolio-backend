"""IngestBatch use case -- command DTO.

`roles` are raw incoming role dicts in the same shape ingest.js has always
produced (see profile/job-search/dashboard/lib/identity.js callers) -- title,
company, and whatever of the flat JobApplication fields the scraper filled in.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IngestBatchCommand:
    roles: list[dict[str, Any]]
    replace: bool = False
