"""ApplyLiveness use case -- response DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApplyLivenessResponse:
    matched: int
    retired: int
    work_mode_corrected: int
    jd_url_corrected: int
    unmatched: list[str] = field(default_factory=list)
    approved_died: list[str] = field(default_factory=list)
