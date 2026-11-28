"""GetSearchStats use case: which searches bring roles.

The unit is one search: a line (a search string, a LinkedIn section such as "Top picks",
a board browsed, an alert email) on one portal. Every run uploads one `line_yield` entry
per search it executed (record-run.js), so summing those entries across runs gives, per
search: how many times it ran, how many cards it surfaced, how many were new after
dedupe, read, passed and flagged. The roles themselves add what Richard did with them
(approved, applied, rejected), through `discovery_queries`.

Repeats count on purpose: a search that surfaces the same good role twice still did its
job. Nothing is stored; everything is computed from the runs and roles at read time.
"""

from collections import defaultdict
from typing import Any, Optional

from backend.application.applications.get_feedback.handler import query_performance
from backend.application.applications.ports.application_repository import IJobApplicationRepository
from backend.application.applications.ports.search_run_repository import ISearchRunRepository

RUN_COUNTERS = ("surfaced", "new", "read", "passed", "flagged")
ROLE_COUNTERS = ("roles", "approved", "applied", "rejected")

TECHNIQUES = ("search_string", "section", "board", "alert", "other")


def technique_of(entry: dict[str, Any]) -> str:
    """The agent sends `technique` from now on; older entries are classified by shape."""
    stated = entry.get("technique")
    if stated in TECHNIQUES:
        return stated
    line = str(entry.get("line") or "").lower()
    portal = str(entry.get("portal") or "").lower()
    if line.startswith(("linkedin_section", "section:")) or "top picks" in line or "recommended" in line:
        return "section"
    if "alert" in line or "email" in line:
        return "alert"
    if "harvest" in line or "unattributed" in line:
        return "other"
    if portal == "linkedin" or '"' in line or "@" in line:
        return "search_string"
    return "board"


def _num(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _empty() -> dict[str, Any]:
    return {key: 0 for key in RUN_COUNTERS + ROLE_COUNTERS} | {"executions": 0}


def _add(row: dict[str, Any], entry: dict[str, Any]) -> None:
    row["executions"] += 1
    row["surfaced"] += _num(entry.get("surfaced"))
    row["new"] += _num(entry.get("new_after_dedupe"))
    row["read"] += _num(entry.get("read"))
    row["passed"] += _num(entry.get("passed"))
    row["flagged"] += _num(entry.get("flagged"))


def search_stats(runs: list[dict[str, Any]], role_verdicts: dict[str, dict[str, int]]) -> dict[str, Any]:
    searches: dict[tuple[str, str], dict[str, Any]] = {}
    by_technique: dict[str, dict[str, Any]] = defaultdict(_empty)
    by_portal: dict[str, dict[str, Any]] = defaultdict(_empty)
    timeline: list[dict[str, Any]] = []

    for run in sorted(runs, key=lambda r: str(r.get("run_date"))):
        run_date = str(run.get("run_date"))[:10]
        entries = [e for e in (run.get("line_yield") or []) if isinstance(e, dict) and e.get("line")]
        point = _empty() | {"run_date": run_date, "searches": len(entries)}
        for entry in entries:
            line, portal = str(entry["line"]), str(entry.get("portal") or "unknown")
            technique = technique_of(entry)
            row = searches.setdefault(
                (portal, line),
                _empty() | {"line": line, "portal": portal, "technique": technique, "first_run": run_date, "history": []},
            )
            row["technique"] = technique  # the latest classification wins
            row["last_run"] = run_date
            _add(row, entry)
            row["history"].append({
                "run_date": run_date,
                "surfaced": _num(entry.get("surfaced")),
                "new": _num(entry.get("new_after_dedupe")),
                "passed": _num(entry.get("passed")),
            })
            _add(by_technique[technique], entry)
            _add(by_portal[portal], entry)
            _add(point, entry)
        point["executions"] = len(entries)
        if entries:
            timeline.append(point)

    # What Richard did with the roles each line found (line strings carry no portal).
    for row in searches.values():
        verdicts = role_verdicts.get(row["line"], {})
        row["roles"] = verdicts.get("surfaced", 0)
        for key in ("approved", "applied", "rejected"):
            row[key] = verdicts.get(key, 0)
        row["pass_rate"] = round(row["passed"] / row["new"], 3) if row["new"] else None

    lines = sorted(searches.values(), key=lambda r: (-(r["passed"] + r["approved"]), -r["new"], r["line"]))
    totals = _empty()
    for row in lines:
        for key in RUN_COUNTERS + ("executions",):
            totals[key] += row[key]
    totals["searches"] = len(lines)
    totals["runs"] = len(timeline)
    return {
        "totals": totals,
        "searches": lines,
        "by_technique": dict(by_technique),
        "by_portal": dict(by_portal),
        "timeline": timeline,
    }


class GetSearchStatsHandler:
    def __init__(self, repository: IJobApplicationRepository, run_repository: ISearchRunRepository) -> None:
        self._repository = repository
        self._run_repository = run_repository

    async def execute(self, since: Optional[str] = None) -> dict[str, Any]:
        runs = await self._run_repository.list_all()
        if since:
            runs = [r for r in runs if str(r.get("run_date"))[:10] >= since]
        applications = await self._repository.list(include_archived=True)
        return search_stats(runs, query_performance(applications))
