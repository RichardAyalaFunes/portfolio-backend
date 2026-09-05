"""IngestBatch use case -- handler implementation.

Faithful port of ingest.js's normalize() + fold/merge behavior over
domain.applications.identity:
  - normalize(): score -> band inference, status default, posted_date derived
    from posted_relative when the scraper didn't set it (drives the UI's
    freshness grouping -- this must happen here now that ingest.js itself is
    a thin uploader with no normalization of its own).
  - "posting"/"exact" matches fold into the existing row (new posting id
    prepended unless already present; status/notes preserved unless `replace`).
  - "near" matches are still inserted as a brand-new row, tagged
    possible_duplicate_of in extras for later human review (dedupe.js's job).
  - no match -> brand-new row.
"""

import re
from datetime import date, timedelta
from typing import Any, Optional

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

_RECENT_RE = re.compile(r"minute|hour|hora|momento")
_DAYS_RE = re.compile(r"(\d+)\s*d(?:ay|ays|\b)")
_WEEKS_RE = re.compile(r"(\d+)\s*week")
_MONTHS_RE = re.compile(r"(\d+)\s*month")
_WITHIN_WEEK_RE = re.compile(r"within past week")


def _derive_posted_date(posted_relative: Optional[str], run_date: str) -> tuple[str, str]:
    """Mirrors ingest.js normalize()'s posted_date derivation exactly."""
    text = (posted_relative or "").lower()
    days: Optional[float] = None
    if _RECENT_RE.search(text):
        days = 0
    else:
        m = _DAYS_RE.search(text) or _WEEKS_RE.search(text) or _MONTHS_RE.search(text)
        if m:
            n = int(m.group(1))
            days = n * (7 if "week" in text else 30 if "month" in text else 1)
        elif _WITHIN_WEEK_RE.search(text):
            days = 4  # midpoint guess

    if days is not None:
        run = date.fromisoformat(run_date)
        source = "guessed_midpoint" if _WITHIN_WEEK_RE.search(text) else "derived_from_relative"
        return (run - timedelta(days=days)).isoformat(), source
    return run_date, "run_date_fallback"


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    role = dict(raw)
    score = role.get("score")
    if score is None:
        role["score"] = None
    elif isinstance(score, (int, float)) and (not role.get("band") or role["band"] in ("excellent", "good", "below")):
        role["band"] = "excellent" if score >= 90 else "good" if score >= 75 else "below"

    if not role.get("status"):
        role["status"] = "Dropped" if role.get("band") == "dropped" else "Flagged" if role.get("band") == "flagged" else "To validate"
    if role["status"] not in {s.value for s in Status}:
        role["status"] = Status.TO_VALIDATE.value

    if not role.get("run_date"):
        role["run_date"] = date.today().isoformat()
    if not role.get("posted_date"):
        role["posted_date"], role["posted_date_source"] = _derive_posted_date(role.get("posted_relative"), role["run_date"])

    role["identity_key"] = identity.identity_key(role)
    return role


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

        added = updated = reposts = 0
        near_hits: list[dict[str, Any]] = []

        for incoming in command.roles:
            raw = _normalize(incoming)
            candidates = [a.as_match_candidate() for a in existing]
            match = identity.find_match(raw, candidates)

            if match is None:
                application = JobApplication(
                    id=ApplicationId.generate(),
                    identity_key=raw["identity_key"],
                    title=raw.get("title", ""),
                    company=raw.get("company", ""),
                    group=raw.get("group"),
                    score=raw.get("score"),
                    band=raw.get("band"),
                    status=Status(raw["status"]),
                    postings=[_as_posting(raw)],
                    first_seen=raw["run_date"],
                    last_seen=raw["run_date"],
                    **{f: raw.get(f) for f in FLAT_FIELDS},
                )
                created = await self._repository.create(application)
                existing.append(created)
                added += 1
                continue

            if match.kind in (identity.MatchKind.POSTING, identity.MatchKind.EXACT):
                target = next(a for a in existing if str(a.id) == str(match.role["id"]))
                is_new_posting = target.add_posting(_as_posting(raw))
                target.last_seen = raw["run_date"]
                if is_new_posting and match.kind == identity.MatchKind.EXACT:
                    reposts += 1
                if command.replace:
                    target.status = Status(raw["status"])
                    target.notes = raw.get("notes", target.notes)
                await self._repository.update(target)
                updated += 1
                continue

            # NEAR: inserted as a new row, flagged for dedupe-equivalent review.
            application = JobApplication(
                id=ApplicationId.generate(),
                identity_key=raw["identity_key"],
                title=raw.get("title", ""),
                company=raw.get("company", ""),
                group=raw.get("group"),
                score=raw.get("score"),
                band=raw.get("band"),
                status=Status(raw["status"]),
                postings=[_as_posting(raw)],
                first_seen=raw["run_date"],
                last_seen=raw["run_date"],
                extras={"possible_duplicate_of": str(match.role["id"])},
                **{f: raw.get(f) for f in FLAT_FIELDS},
            )
            created = await self._repository.create(application)
            existing.append(created)
            added += 1
            near_hits.append(
                {"incoming_title": raw.get("title"), "matched_id": str(match.role["id"]), "score": match.score}
            )

        return IngestBatchResponse(added=added, updated=updated, reposts=reposts, total=len(existing), near_hits=near_hits)
