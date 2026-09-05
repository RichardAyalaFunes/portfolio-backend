"""GetApplication use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetApplicationCommand:
    application_id: str
