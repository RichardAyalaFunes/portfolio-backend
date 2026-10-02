"""GetMetrics use case -- response DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricsResponse:
    total: int
    # Roles waiting for Richard's first look, by the same rule as the queue's "To review"
    # bucket (JobApplication.awaits_review). status_counts["To validate"] is the raw
    # status count and also includes roles already applied to or whose posting closed.
    to_review: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    stage_counts: dict[str, int] = field(default_factory=dict)
    funnel_by_group: dict[str, dict[str, int]] = field(default_factory=dict)
    drop_reasons: dict[str, int] = field(default_factory=dict)
    portal_yield: dict[str, dict[str, int]] = field(default_factory=dict)
