"""GetMetrics use case -- response DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricsResponse:
    total: int
    status_counts: dict[str, int] = field(default_factory=dict)
    stage_counts: dict[str, int] = field(default_factory=dict)
    funnel_by_group: dict[str, dict[str, int]] = field(default_factory=dict)
    drop_reasons: dict[str, int] = field(default_factory=dict)
    portal_yield: dict[str, dict[str, int]] = field(default_factory=dict)
