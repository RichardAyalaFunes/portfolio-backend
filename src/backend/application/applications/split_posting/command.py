"""SplitPosting use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SplitPostingCommand:
    application_id: str
    posting_id: str
