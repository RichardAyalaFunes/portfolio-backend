"""GetRules use case -- response DTO.

`content` / `published_at` are None until the agent publishes for the first time; the
two stat maps are always present, computed from the roles as they are right now.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class GetRulesResponse:
    published_at: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    # search line -> {surfaced, approved, rejected, applied}
    line_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    # lane (application.group, "unknown" when unset) -> {total, to_review, flagged, approved, applied, rejected}
    lane_stats: dict[str, dict[str, int]] = field(default_factory=dict)
