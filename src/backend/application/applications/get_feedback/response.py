"""GetFeedback use case -- response DTO."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class FeedbackResponse:
    since: date
    since_source: str  # "request" | "latest_run" | "default_window"
    reviewed: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    query_performance: dict[str, dict[str, int]] = field(default_factory=dict)
    disagreements: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    backlog: dict[str, int] = field(default_factory=dict)
    recent_runs: list[dict[str, Any]] = field(default_factory=list)
