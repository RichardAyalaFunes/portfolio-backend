"""ListApplications use case -- command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ListApplicationsCommand:
    status: Optional[str] = None
    stage: Optional[str] = None
    group: Optional[str] = None
    source: Optional[str] = None
    live_state: Optional[str] = None
    run_date: Optional[str] = None
    query: Optional[str] = None
    sort: Optional[str] = None
