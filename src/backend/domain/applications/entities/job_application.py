"""JobApplication aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from ...shared.base_entity import AggregateRoot
from ..value_objects import APPLIED_STAGES, DEAD_POSTING_STATES, ApplicationId, Stage, Status


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
    skill_match: dict[str, Any] = field(default_factory=dict)
    secondary_lanes: list[str] = field(default_factory=list)
    discovery_queries: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    reviewed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def has_applied(self) -> bool:
        """Any stage after "Not applied", the closed end of the track included."""
        return self.application_stage in APPLIED_STAGES

    @property
    def posting_is_dead(self) -> bool:
        """The liveness sweep found the posting closed, suspended or gone."""
        return self.live_state in DEAD_POSTING_STATES

    @property
    def is_below_bar(self) -> bool:
        """The agent scored the role and it landed under the pass bar, as opposed to a
        gate cutting it before it was scored."""
        return self.drop_stage == "scored" or self.drop_reason == "below_bar"

    @property
    def awaits_review(self) -> bool:
        """Waiting for Richard's first look: no verdict, not applied, the posting is
        still open and the agent did not score it under the bar. The dashboard queue's
        "To review" bucket is this same rule (frontend queueBuckets.ts); the metrics and
        rules counters use this one so the numbers agree."""
        return (
            self.status == Status.TO_VALIDATE
            and self.application_stage == Stage.NOT_APPLIED
            and not self.posting_is_dead
            and not self.is_below_bar
        )

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

    def mark_reviewed(self) -> None:
        """Richard gave feedback (status, stage or a note). Only the human paths call
        this -- the dashboard PATCH and annotate -- never ingest, so GET /feedback can
        tell his decisions apart from the agent's own writes."""
        self.reviewed_at = datetime.now(tz=timezone.utc)

    def add_discovery_queries(self, queries: list[str]) -> None:
        """Union, keeping first-seen order: a role found again by another line keeps
        the credit for every line that ever surfaced it."""
        for query in queries:
            if query and query not in self.discovery_queries:
                self.discovery_queries.append(query)

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

    def set_skill_match(self, payload: dict[str, Any]) -> None:
        """Replace the JD-requirements-vs-CV/LinkedIn table wholesale. `payload` is what
        domain.applications.skill_match.normalize_skill_match returned, or {} to clear.
        An agent write like contacts/application_form, never a review: it does not
        call mark_reviewed()."""
        self.skill_match = payload

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
