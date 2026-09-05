"""IngestBatch use case -- response DTO.

Structured counts only -- the CLI wrapper (ingest.js, post-cutover) is
responsible for formatting these into the same console report it prints
today, matching docs/job-dashboard-plan.md ss5.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IngestBatchResponse:
    added: int
    updated: int
    reposts: int
    near_hits: list[dict[str, Any]] = field(default_factory=list)
