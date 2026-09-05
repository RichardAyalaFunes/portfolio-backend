"""UpdateApplication use case -- response DTO."""

from dataclasses import dataclass

from backend.domain.applications.entities.job_application import JobApplication


@dataclass(frozen=True)
class UpdateApplicationResponse:
    application: JobApplication
