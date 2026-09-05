"""ApplyLiveness use case -- handler implementation.

Faithful port of apply-liveness.js's effects: always stamp live_state/
live_checked_at; correct jd_url and work_mode when the sweep disagrees;
auto-retire To validate/Flagged roles to Cold when a posting died, but only
report (never touch) an Approved role whose posting died -- that needs a
human decision.
"""

from datetime import date

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications.value_objects import Status

from .command import ApplyLivenessCommand
from .port import IApplyLivenessUseCase
from .response import ApplyLivenessResponse

_DEAD_STATES = {"CLOSED", "SUSPENDED", "GONE"}
_AUTO_RETIRE_FROM = {Status.TO_VALIDATE, Status.FLAGGED}


class ApplyLivenessHandler(IApplyLivenessUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: ApplyLivenessCommand) -> ApplyLivenessResponse:
        existing = await self._repository.list(include_archived=False)
        today = date.today().isoformat()

        matched = retired = work_mode_corrected = jd_url_corrected = 0
        unmatched: list[str] = []
        approved_died: list[str] = []

        for posting_id, info in command.sweep.items():
            application = next(
                (
                    a
                    for a in existing
                    if str(a.id) == posting_id or any(str(p.get("id")) == posting_id for p in a.postings)
                ),
                None,
            )
            if application is None:
                unmatched.append(posting_id)
                continue
            matched += 1

            application.live_state = info.get("state")
            application.live_checked_at = today

            new_url = info.get("url")
            if new_url and new_url != application.jd_url:
                application.extras["jd_url_previous"] = application.jd_url
                application.jd_url = new_url
                jd_url_corrected += 1

            remote = info.get("remote")
            if remote is not None:
                application.work_remote_allowed = remote
                if remote is False and application.work_mode and "remote" in application.work_mode.lower():
                    application.extras["work_mode_previous"] = application.work_mode
                    application.work_mode = "On-site / hybrid (LinkedIn workplace tag)"
                    work_mode_corrected += 1

            if info.get("state") in _DEAD_STATES:
                if application.status in _AUTO_RETIRE_FROM:
                    application.extras["status_previous"] = application.status.value
                    application.extras["cold_reason"] = f"posting closed (verified {today})"
                    application.status = Status.COLD
                    retired += 1
                elif application.status == Status.APPROVED:
                    approved_died.append(str(application.id))

            await self._repository.update(application)

        return ApplyLivenessResponse(
            matched=matched,
            retired=retired,
            work_mode_corrected=work_mode_corrected,
            jd_url_corrected=jd_url_corrected,
            unmatched=unmatched,
            approved_died=approved_died,
        )
