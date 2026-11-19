"""UpdateApplication use case -- command DTO. Only supplied fields change."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UpdateApplicationCommand:
    application_id: str
    status: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    jd_url: Optional[str] = None
    # Only the value duplicate is known: the role is rejected because it repeats another one.
    rejection_reason: Optional[str] = None
