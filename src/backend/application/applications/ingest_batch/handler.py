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
  - search-feedback fields (secondary_lanes, discovery_queries, tags) are the
    agent's own facts: discovery_queries are unioned on a fold so a line keeps
    credit for every role it ever surfaced; secondary_lanes and tags are replaced
    by the latest run that reports them. reviewed_at is never touched here.
"""

import re
from datetime import date, timedelta
from typing import Any, Optional

from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.domain.applications import identity, returns
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


# Sources that are the platform's own timestamp. Anything else is an estimate from a
# relative phrase ("2 days ago") or the day we found the role.
REAL_DATE_SOURCES = frozenset({"linkedin_listedAt"})


def _apply_real_posted_date(target: JobApplication, raw: dict[str, Any]) -> None:
    """A re-sent role carrying the platform's real listing date corrects the estimate
    stored earlier. An estimate never replaces anything already on the row."""
    if raw.get("posted_date_source") not in REAL_DATE_SOURCES or not raw.get("posted_date"):
        return
    day = str(raw["posted_date"])[:10]
    target.posted_date = date.fromisoformat(day)
    target.posted_date_source = raw["posted_date_source"]
    for posting in target.postings:
        if posting.get("id") == raw.get("id"):
            posting["posted_date"] = day


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

    role["secondary_lanes"] = _str_list(role.get("secondary_lanes"))
    role["tags"] = [_slug(t) for t in _str_list(role.get("tags"))]
    queries = _str_list(role.get("discovery_queries"))
    if not queries and role.get("found_by_query"):
        queries = [role["found_by_query"]]
    role["discovery_queries"] = queries

    role["identity_key"] = identity.identity_key(role)
    return role


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    seen: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", tag.lower()).strip("_")


def _feedback_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "secondary_lanes": raw["secondary_lanes"],
        "discovery_queries": raw["discovery_queries"],
        "tags": raw["tags"],
    }


def _as_posting(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "url": raw.get("jd_url"),
        "source": raw.get("source"),
        "run_date": raw.get("run_date"),
        "posted_date": raw.get("posted_date"),
        "live_state": raw.get("live_state"),
    }


def _snapshot(application: JobApplication) -> dict[str, Any]:
    """The few facts a comeback record compares against, taken before the fold."""
    fields = ("title", "salary_text", "location_text", "work_mode", "employment_type",
              "score", "band", "drop_reason", "drop_stage")
    out: dict[str, Any] = {name: getattr(application, name) for name in fields}
    out["status"] = application.status
    return out


class IngestBatchHandler(IIngestBatchUseCase):
    def __init__(self, repository: IJobApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, command: IngestBatchCommand) -> IngestBatchResponse:
        existing = await self._repository.list(include_archived=False)

        added = updated = reposts = 0
        near_hits: list[dict[str, Any]] = []
        returned: list[dict[str, Any]] = []
        # Days a search ran and uploaded: the dates any row was first or last seen. A role
        # only "came back" if a search between its last sighting and now could have seen it
        # gone; otherwise it was just never looked for.
        search_days = {d for a in existing for d in (a.first_seen, a.last_seen) if d is not None}

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
                    **_feedback_fields(raw),
                    **{f: raw.get(f) for f in FLAT_FIELDS},
                )
                created = await self._repository.create(application)
                existing.append(created)
                added += 1
                continue

            if match.kind in (identity.MatchKind.POSTING, identity.MatchKind.EXACT):
                target = next(a for a in existing if str(a.id) == str(match.role["id"]))
                # Read the row as it was before this fold touches it: the comeback record
                # keeps what the role looked like when it went away.
                before = _snapshot(target)
                previous_last_seen = target.last_seen or target.first_seen
                is_new_posting = target.add_posting(_as_posting(raw))
                target.last_seen = raw["run_date"]
                _apply_real_posted_date(target, raw)
                target.add_discovery_queries(raw["discovery_queries"])
                if "secondary_lanes" in incoming:
                    target.secondary_lanes = raw["secondary_lanes"]
                if "tags" in incoming:
                    target.tags = raw["tags"]
                if is_new_posting and match.kind == identity.MatchKind.EXACT:
                    reposts += 1
                    comeback = self._record_return(target, raw, before, previous_last_seen, search_days)
                    if comeback is not None:
                        returned.append(comeback)
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
                **_feedback_fields(raw),
                **{f: raw.get(f) for f in FLAT_FIELDS},
            )
            created = await self._repository.create(application)
            existing.append(created)
            added += 1
            near_hits.append(
                {"incoming_title": raw.get("title"), "matched_id": str(match.role["id"]), "score": match.score}
            )

        return IngestBatchResponse(added=added, updated=updated, reposts=reposts, total=len(existing), near_hits=near_hits, returned=returned)


    def _record_return(
        self,
        target: JobApplication,
        raw: dict[str, Any],
        before: dict[str, Any],
        previous_last_seen: Any,
        search_days: set[Any],
    ) -> Optional[dict[str, Any]]:
        """A role we hold was posted again under a new posting id. Decide whether that is
        a comeback (see domain.applications.returns), record it in extras["returns"], and
        move the row back into the review queue when the rules say so. Returns the short
        summary for the ingest response, or None when it is not a comeback."""
        gap = returns.gap_days(previous_last_seen, raw["run_date"])
        kind = returns.classify(
            gap=gap,
            is_new_posting=True,
            searched_between=returns.searched_between(previous_last_seen, raw["run_date"], search_days),
        )
        if kind is None:
            return None

        history = returns.returns_of(target.extras)
        decision = returns.decide_status(
            status=before["status"],
            incoming_status=Status(raw["status"]),
            has_applied=target.has_applied,
            previous_returns=len(history),
            is_duplicate=target.is_duplicate,
        )
        prior = returns.prior_decision(
            status=before["status"],
            reviewed_at=target.reviewed_at,
            last_seen=previous_last_seen,
            drop_reason=before["drop_reason"],
            drop_stage=before["drop_stage"],
            score=before["score"],
            application_stage=target.application_stage.value if target.has_applied else None,
        )
        event = returns.build_event(
            kind=kind,
            gap=gap,
            run_date=raw["run_date"],
            previous_last_seen=previous_last_seen,
            posting_id=raw.get("id"),
            posting_url=raw.get("jd_url"),
            prior=prior,
            decision=decision,
            changes=returns.changes_between(before, raw),
        )
        target.extras = {**target.extras, "returns": [*history, event]}

        if decision.reset:
            # The new posting is the current truth: take its facts, keep Richard's notes,
            # review stamp and application stage.
            target.status = decision.new_status
            for name in ("title", "group", "score", "band"):
                if raw.get(name) is not None:
                    setattr(target, name, raw[name])
            for name in returns.REFRESH_FIELDS:
                value = raw.get(name)
                if value is not None or name in returns.CLEAR_WHEN_ABSENT:
                    setattr(target, name, value)

        return {
            "id": str(target.id),
            "company": target.company,
            "title": target.title,
            "kind": kind,
            "gap_days": gap,
            "prior_status": prior["status"],
            "prior_decided_by": prior["decided_by"],
            "status_after": decision.new_status.value,
            "status_reset": decision.reset,
            "alert": decision.alert,
            "evergreen": len(history) + 1 >= returns.EVERGREEN_AFTER,
        }
