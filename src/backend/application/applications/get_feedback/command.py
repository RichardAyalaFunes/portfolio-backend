"""GetFeedback use case -- command DTO.

since: only roles Richard reviewed on or after this date. None means "since the
latest recorded search run" (falls back to DEFAULT_WINDOW_DAYS when no run exists).
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class GetFeedbackCommand:
    since: Optional[date] = None
    recent_runs: int = 5
