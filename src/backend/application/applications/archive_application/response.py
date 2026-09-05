"""ArchiveApplication use case -- response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveApplicationResponse:
    application_id: str
