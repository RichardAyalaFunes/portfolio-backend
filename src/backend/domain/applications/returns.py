"""When a role we already hold comes back as a new posting.

A merge on ingest used to be silent: the old row kept its status and nobody could
tell that a role Richard rejected in October, or the agent dropped in June, had been
re-posted. This module holds the rules, as pure functions, so they can be tested
without a repository:

  - classify(): is this a repost, a reopening, or just the same ad seen again?
  - decide_status(): what a returning role does to the stored status.
  - build_event(): the record kept in `extras["returns"]`, one per comeback.

Thresholds (Richard, 2026-11-17): 7 days is the line between "the same ad" and a repost,
90 days the line between a repost and a reopening. They are constants here, not settings,
because the dashboard text ("Reposted 35 days after you rejected it") is written against them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Optional

from .value_objects import Status

REPOST_AFTER_DAYS = 7
REOPEN_AFTER_DAYS = 90
# A row that keeps coming back (an agency that re-lists the same ad every month) stops
# being news after this many comebacks: still recorded, no longer resets the status.
EVERGREEN_AFTER = 3

KIND_REPOSTED = "reposted"
KIND_REOPENED = "reopened"

# Statuses a comeback may move back to "To validate": the role was set aside and the new
# posting is a reason to look again. Approved is never reset (he already said yes) and a
# row that is still waiting needs no reset.
RESURFACE_FROM = frozenset({Status.REJECTED, Status.DROPPED, Status.COLD})
# What the new scoring may put a resurfaced role back to. If the agent scored the new
# posting as Dropped again (the rules still do not let it through), the old status stays.
RESURFACE_TO = frozenset({Status.TO_VALIDATE, Status.FLAGGED})

# Facts the agent re-reads from the new posting. Refreshed only when the role resurfaces.
REFRESH_FIELDS = (
    "group", "score", "band", "location_text", "work_mode", "employment_type", "salary_text",
    "posted_date", "posted_date_source", "posted_relative", "eligibility_text",
    "requirements_excerpt", "why_apply", "why_not", "considerations", "jd_url", "source",
    "found_by_query", "run_date", "live_state", "live_checked_at", "work_remote_allowed",
    "drop_stage", "drop_reason",
)
# Fields whose old and new value are worth showing side by side in the history.
COMPARE_FIELDS = ("title", "salary_text", "location_text", "work_mode", "employment_type", "score", "band")
# These must be cleared when the new posting has none (a role dropped for a reason no longer has it).
CLEAR_WHEN_ABSENT = frozenset({"drop_stage", "drop_reason"})


def to_date(value: Any) -> Optional[date]:
    """Rows hold dates as `date`; incoming roles and old rows can hold ISO strings."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def gap_days(previous_last_seen: Any, run_date: Any) -> Optional[int]:
    before, after = to_date(previous_last_seen), to_date(run_date)
    if before is None or after is None:
        return None
    return (after - before).days


def classify(
    *,
    gap: Optional[int],
    is_new_posting: bool,
    searched_between: bool,
) -> Optional[str]:
    """None means "not a comeback": the same ad, a country copy posted the same week, or a
    gap we could not have seen.

    - A posting id we already hold is the same ad however long it was missing: our search
      simply did not find it in between.
    - `searched_between` is False when no search ran between the last sighting and now.
      Then the role never had the chance to be seen as gone, so nothing "came back"."""
    if not is_new_posting or gap is None or gap < REPOST_AFTER_DAYS or not searched_between:
        return None
    return KIND_REOPENED if gap > REOPEN_AFTER_DAYS else KIND_REPOSTED


def searched_between(previous_last_seen: Any, run_date: Any, search_days: Iterable[Any]) -> bool:
    """True if some search day lies strictly between the two dates. `search_days` are the
    dates the dashboard has any role from (first/last seen): each is a day a search ran and
    its results were uploaded."""
    before, after = to_date(previous_last_seen), to_date(run_date)
    if before is None or after is None:
        return False
    for day in search_days:
        d = to_date(day)
        if d is not None and before < d < after:
            return True
    return False


@dataclass(frozen=True)
class Decision:
    reset: bool
    new_status: Status
    alert: Optional[str] = None


def decide_status(
    *,
    status: Status,
    incoming_status: Status,
    has_applied: bool,
    previous_returns: int,
    is_duplicate: bool = False,
) -> Decision:
    """What the comeback does to the stored status. Never touches notes or the application
    stage. Order matters: an application he sent outranks everything."""
    if has_applied:
        # He applied before. A repost can mean the process stalled or the role was reopened
        # for another profile; tell him, change nothing.
        return Decision(reset=False, new_status=status, alert="applied_before")
    if previous_returns >= EVERGREEN_AFTER:
        return Decision(reset=False, new_status=status)
    if is_duplicate:
        # Rejected for repeating another role; a new posting of it is still that copy.
        return Decision(reset=False, new_status=status)
    if status in RESURFACE_FROM and incoming_status in RESURFACE_TO:
        return Decision(reset=True, new_status=incoming_status)
    return Decision(reset=False, new_status=status)


def prior_decision(
    *,
    status: Status,
    reviewed_at: Any,
    last_seen: Any,
    drop_reason: Optional[str],
    drop_stage: Optional[str],
    score: Optional[int],
    application_stage: Optional[str],
) -> dict[str, Any]:
    """Who closed the role last, and when. `reviewed_at` is only ever set by Richard (the
    dashboard PATCH and annotate), so its presence is what separates his rejection from the
    agent's drop."""
    decided_by = "you" if reviewed_at is not None else "agent"
    decided_on = to_date(reviewed_at) or to_date(last_seen)
    return {
        "status": status.value,
        "decided_by": decided_by,
        "decided_on": decided_on.isoformat() if decided_on else None,
        "drop_reason": drop_reason,
        "drop_stage": drop_stage,
        "score": score,
        "application_stage": application_stage,
    }


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def changes_between(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """{field: [old, new]} for the fields that really changed. A field the new posting
    does not mention is not a change."""
    out: dict[str, list[Any]] = {}
    for key in COMPARE_FIELDS:
        new_value = new.get(key)
        if new_value is None:
            continue
        old_value = old.get(key)
        if _plain(old_value) != _plain(new_value):
            out[key] = [_plain(old_value), _plain(new_value)]
    return out


def build_event(
    *,
    kind: str,
    gap: int,
    run_date: Any,
    previous_last_seen: Any,
    posting_id: Any,
    posting_url: Optional[str],
    prior: dict[str, Any],
    decision: Decision,
    changes: dict[str, list[Any]],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "at": _plain(to_date(run_date)),
        "gap_days": gap,
        "previous_last_seen": _plain(to_date(previous_last_seen)),
        "posting_id": posting_id,
        "posting_url": posting_url,
        "prior": prior,
        "status_reset": decision.reset,
        "status_after": decision.new_status.value,
        "alert": decision.alert,
        "changes": changes,
    }


def returns_of(extras: dict[str, Any]) -> list[dict[str, Any]]:
    value = extras.get("returns") if extras else None
    return value if isinstance(value, list) else []
