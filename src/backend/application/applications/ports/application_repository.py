"""IJobApplicationRepository -- driven port for job_applications persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId


class IJobApplicationRepository(ABC):
    """Driven port -- the application layer only depends on this interface."""

    @abstractmethod
    async def list(
        self,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        group: Optional[str] = None,
        source: Optional[str] = None,
        live_state: Optional[str] = None,
        run_date: Optional[str] = None,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[JobApplication]:
        """No filters + include_archived=False returns the full working set --
        used as-is by ingest/metrics, which need every non-archived row for
        identity matching / aggregation (small dataset, see
        docs/job-dashboard-plan.md; fine at this scale)."""

    @abstractmethod
    async def get(self, application_id: ApplicationId) -> Optional[JobApplication]:
        ...

    @abstractmethod
    async def get_by_identity_key(self, identity_key: str) -> Optional[JobApplication]:
        ...

    @abstractmethod
    async def create(self, application: JobApplication) -> JobApplication:
        ...

    @abstractmethod
    async def update(self, application: JobApplication) -> JobApplication:
        """Full update of an existing row, keyed by application.id."""
