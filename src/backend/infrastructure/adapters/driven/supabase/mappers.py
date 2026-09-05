"""Row <-> JobApplication mapping shared by the Supabase repositories."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId, Stage, Status

FLAT_FIELDS = (
    "legacy_id", "group", "score", "band", "location_text", "work_mode",
    "employment_type", "salary_text", "posted_date_source", "posted_relative",
    "eligibility_text", "requirements_excerpt", "why_apply", "why_not",
    "considerations", "jd_url", "source", "found_by_query", "live_state",
    "work_remote_allowed", "drop_stage", "drop_reason", "notes",
)
DATE_FIELDS = ("posted_date", "run_date", "first_seen", "last_seen", "live_checked_at", "notes_updated_at")
DATETIME_FIELDS = ("archived_at", "created_at", "updated_at")


def _parse_date(value: Any) -> Optional[date]:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def row_to_entity(row: dict[str, Any]) -> JobApplication:
    kwargs: dict[str, Any] = {f: row.get(f) for f in FLAT_FIELDS}
    for f in DATE_FIELDS:
        kwargs[f] = _parse_date(row.get(f))
    for f in DATETIME_FIELDS:
        kwargs[f] = _parse_datetime(row.get(f))

    return JobApplication(
        id=ApplicationId.from_string(row["id"]),
        identity_key=row["identity_key"],
        title=row["title"],
        company=row["company"],
        status=Status(row["status"]),
        application_stage=Stage(row.get("application_stage") or Stage.NOT_APPLIED.value),
        postings=row.get("postings") or [],
        extras=row.get("extras") or {},
        **kwargs,
    )


def entity_to_row(application: JobApplication) -> dict[str, Any]:
    row: dict[str, Any] = {f: getattr(application, f) for f in FLAT_FIELDS}
    for f in DATE_FIELDS:
        value = getattr(application, f)
        row[f] = value.isoformat() if isinstance(value, date) else value
    for f in DATETIME_FIELDS:
        value = getattr(application, f)
        row[f] = value.isoformat() if isinstance(value, datetime) else value

    row.update(
        {
            "id": str(application.id),
            "identity_key": application.identity_key,
            "title": application.title,
            "company": application.company,
            "status": application.status.value,
            "application_stage": application.application_stage.value,
            "postings": application.postings,
            "extras": application.extras,
        }
    )
    return row
