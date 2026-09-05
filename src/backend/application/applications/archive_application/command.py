"""ArchiveApplication use case -- command DTO (soft delete)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveApplicationCommand:
    application_id: str
