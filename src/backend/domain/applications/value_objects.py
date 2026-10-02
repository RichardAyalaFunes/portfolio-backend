"""Job applications domain — value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID, uuid4

from ..shared.base_value_object import ValueObject
from ..shared.errors import InvalidValueError


@dataclass(frozen=True)
class ApplicationId(ValueObject):
    """Unique identifier for a JobApplication aggregate (Supabase uuid pk)."""

    value: UUID

    @staticmethod
    def generate() -> "ApplicationId":
        return ApplicationId(value=uuid4())

    @staticmethod
    def from_string(value: str) -> "ApplicationId":
        if not value:
            raise InvalidValueError("ApplicationId cannot be empty")
        try:
            return ApplicationId(value=UUID(value))
        except ValueError as exc:
            raise InvalidValueError(f"ApplicationId is not a valid UUID: {value!r}") from exc

    def __str__(self) -> str:
        return str(self.value)


class Status(str, Enum):
    """Review status — describes where the role stands in Richard's screening pipeline."""

    TO_VALIDATE = "To validate"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    COLD = "Cold"
    FLAGGED = "Flagged"
    DROPPED = "Dropped"


class Stage(str, Enum):
    """Application progress — separate from Status; a role can be Approved and still Not applied."""

    NOT_APPLIED = "Not applied"
    APPLIED = "Applied"
    INTERVIEWING = "Interviewing"
    OFFER = "Offer"
    CLOSED = "Closed"


# Every stage after "Not applied": the application was sent. Closed is the end of that
# track (the process is over), so a closed application still counts as one he made.
APPLIED_STAGES = (Stage.APPLIED, Stage.INTERVIEWING, Stage.OFFER, Stage.CLOSED)

# What the liveness sweep reports for a posting that no longer takes applications.
# Anything else (LISTED, UNVERIFIABLE, never checked) counts as open.
DEAD_POSTING_STATES = frozenset({"CLOSED", "SUSPENDED", "GONE"})
