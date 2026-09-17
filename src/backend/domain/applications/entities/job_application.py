"""JobApplication aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from ...shared.base_entity import AggregateRoot
from ..value_objects import ApplicationId, Stage, Status


@dataclass
class JobApplication(AggregateRoot[ApplicationId]):
    """
    Aggregate root for one tracked job application.

    Most fields are plain review data carried over from the original local
    tool (see docs/job-dashboard-plan.md ss3.1) — the actual invariants this
    aggregate protects are narrower: soft delete, notes bookkeeping, and
    posting de-duplication on ingest. Status/stage are intentionally NOT a
    constrained state machine (unlike AvatarSession) -- Richard moves roles
    between any status or stage freely while reviewing, there is no
    forbidden-transition set here.
    """

    identity_key: str = ""
    title: str = ""
    company: str = ""
    status: Status = Status.TO_VALIDATE
    application_stage: Stage = Stage.NOT_APPLIED

    legacy_id: Optional[str] = None
    group: Optional[str] = None
    score: Optional[int] = None
    band: Optional[str] = None
    location_text: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    salary_text: Optional[str] = None
    posted_date: Optional[date] = None
    posted_date_source: Optional[str] = None
    posted_relative: Optional[str] = None
    eligibility_text: Optional[str] = None
    requirements_excerpt: Optional[str] = None
    why_apply: Optional[str] = None
    why_not: Optional[str] = None
    considerations: Optional[str] = None
    jd_url: Optional[str] = None
    source: Optional[str] = None
    found_by_query: Optional[str] = None
    run_date: Optional[date] = None
    first_seen: Optional[date] = None
    last_seen: Optional[date] = None
    live_state: Optional[str] = None
    live_checked_at: Optional[date] = None
    work_remote_allowed: Optional[bool] = None
    drop_stage: Optional[str] = None
    drop_reason: Optional[str] = None
    notes: str = ""
    notes_updated_at: Optional[date] = None
    postings: list[dict[str, Any]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    application_form: dict[str, Any] = field(default_factory=dict)
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self) -> None:
        """Soft delete -- row is hidden but kept for history and dedupe."""
        self.archived_at = datetime.now(tz=timezone.utc)

    def restore(self) -> None:
        self.archived_at = None

    def update_notes(self, text: str) -> None:
        self.notes = text
        self.notes_updated_at = datetime.now(tz=timezone.utc).date()

    def set_status(self, status: Status) -> None:
        self.status = status

    def set_stage(self, stage: Stage) -> None:
        self.application_stage = stage

    def add_posting(self, posting: dict[str, Any]) -> bool:
        """Append a posting if its id isn't already recorded. Returns True if added."""
        posting_id = posting.get("id")
        if posting_id is not None and any(p.get("id") == posting_id for p in self.postings):
            return False
        self.postings.insert(0, posting)
        return True

    def set_contacts(self, contacts: list[dict[str, Any]]) -> None:
        """Replace the outreach contact list wholesale -- the enrichment step always
        sends its full current picture for a role, there is nothing to merge
        item-by-item. Preserves each existing contact's own `outreach_stage` (and its
        timestamp) by matching on `id`/`linkedin_slug`, since that field is Richard's
        to move, not the agent's to reset on a re-run."""
        prior = {c.get("id") or c.get("linkedin_slug"): c for c in self.contacts}
        for contact in contacts:
            key = contact.get("id") or contact.get("linkedin_slug")
            existing = prior.get(key)
            if existing and existing.get("outreach_stage"):
                contact["outreach_stage"] = existing["outreach_stage"]
                contact["outreach_stage_updated_at"] = existing.get("outreach_stage_updated_at")
        self.contacts = contacts

    def set_application_form(self, application_form: dict[str, Any]) -> None:
        self.application_form = application_form

    def update_contact_stage(self, contact_id: str, stage: str) -> bool:
        """Richard's one write to this structure. Returns False if no contact matches."""
        for contact in self.contacts:
            if contact.get("id") == contact_id:
                contact["outreach_stage"] = stage
                contact["outreach_stage_updated_at"] = datetime.now(tz=timezone.utc).date().isoformat()
                return True
        return False

    def as_match_candidate(self) -> dict[str, Any]:
        """The plain-dict shape domain.applications.identity.find_match expects."""
        return {
            "id": str(self.id),
            "company": self.company,
            "title": self.title,
            "identity_key": self.identity_key,
            "postings": self.postings,
        }
