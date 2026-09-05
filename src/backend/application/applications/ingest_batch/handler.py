"""IngestBatch use case -- handler implementation.

Faithful port of ingest.js's fold/merge behavior over domain.applications.identity:
  - "posting"/"exact" matches fold into the existing row (new posting id
    prepended unless already present; status/notes preserved unless `replace`).
  - "near" matches are still inserted as a brand-new row, tagged
    possible_duplicate_of in extras for later human review (dedupe.js's job).
  - no match -> brand-new row.
"""

from datetime import date
from typing import Any

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications import identity
from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId, Status

from .command import IngestBatchCommand
from .port import IIngestBatchUseCase
from .response import IngestBatchResponse

FLAT_FIELDS = (
    "location_text", "work_mode", "employment_type", "salary_text",
    "posted_date", "posted_date_source", "posted_relative", "eligibility_text",
    "requirements_excerpt", "why_apply", "why_not", "considerations", "jd_url",
    "source", "found_by_query", "run_date", "live_state", "live_checked_at",
    "work_remote_allowed", "drop_stage", "drop_reason",
)


def _as_posting(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "url": raw.get("jd_url"),
        "source": raw.get("source"),
        "run_date": raw.get("run_date"),
        "posted_date": raw.get("posted_date"),
        "live_state": raw.get("live_state"),
    }


class IngestBatchHandler(IIngestBatchUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: IngestBatchCommand) -> IngestBatchResponse:
        existing = await self._repository.list(include_archived=False)
        today = date.today().isoformat()

        added = updated = reposts = 0
        near_hits: list[dict[str, Any]] = []

        for raw in command.roles:
            candidates = [a.as_match_candidate() for a in existing]
            match = identity.find_match(raw, candidates)

            if match is None:
                application = JobApplication(
                    id=ApplicationId.generate(),
                    identity_key=identity.identity_key(raw),
                    title=raw.get("title", ""),
                    company=raw.get("company", ""),
                    group=raw.get("group"),
                    score=raw.get("score"),
                    band=raw.get("band"),
                    status=Status(raw.get("status") or Status.TO_VALIDATE.value),
                    postings=[_as_posting(raw)],
                    first_seen=today,
                    last_seen=today,
                    **{f: raw.get(f) for f in FLAT_FIELDS},
                )
                created = await self._repository.create(application)
                existing.append(created)
                added += 1
                continue

            if match.kind in (identity.MatchKind.POSTING, identity.MatchKind.EXACT):
                target = next(a for a in existing if str(a.id) == str(match.role["id"]))
                is_new_posting = target.add_posting(_as_posting(raw))
                target.last_seen = today
                if is_new_posting and match.kind == identity.MatchKind.EXACT:
                    reposts += 1
                if command.replace:
                    target.status = Status(raw.get("status") or target.status.value)
                    target.notes = raw.get("notes", target.notes)
                await self._repository.update(target)
                updated += 1
                continue

            # NEAR: inserted as a new row, flagged for dedupe.js-equivalent review.
            application = JobApplication(
                id=ApplicationId.generate(),
                identity_key=identity.identity_key(raw),
                title=raw.get("title", ""),
                company=raw.get("company", ""),
                group=raw.get("group"),
                score=raw.get("score"),
                band=raw.get("band"),
                status=Status(raw.get("status") or Status.TO_VALIDATE.value),
                postings=[_as_posting(raw)],
                first_seen=today,
                last_seen=today,
                extras={"possible_duplicate_of": str(match.role["id"])},
                **{f: raw.get(f) for f in FLAT_FIELDS},
            )
            created = await self._repository.create(application)
            existing.append(created)
            added += 1
            near_hits.append(
                {"incoming_title": raw.get("title"), "matched_id": str(match.role["id"]), "score": match.score}
            )

        return IngestBatchResponse(added=added, updated=updated, reposts=reposts, near_hits=near_hits)
