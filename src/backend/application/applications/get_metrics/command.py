"""GetMetrics use case -- command DTO. scope: 'all' | 'latest' | 'week' | 'run:YYYY-MM-DD'."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetMetricsCommand:
    scope: str = "all"
