"""Skill match: JD requirements vs Richard's real experience vs what his CV and
LinkedIn show. Pure validation and normalisation, no I/O.

Why this exists: recruiters only ever see two documents, the CV and the LinkedIn
profile. A requirement Richard genuinely meets but neither document shows is the
cheapest thing to fix before applying, so each row of the table answers three
questions about one JD requirement: does his experience match it, does the CV show
it, does LinkedIn show it. The job-search agent writes the table through an
ingest-key endpoint and the dashboard only reads it.

The server owns the shape. Input is validated, trimmed and normalised, and the
`summary` counters are always recomputed here from the rows: a `summary` (or any
other unknown key) in the input is ignored, never trusted. Anything invalid raises
InvalidValueError with a message that names the offending field, because the
caller is an agent that has to fix its payload and retry.

Deliberately strict about values: a level or kind that is not one of the literals
below (case included) is an error rather than a guess, so a wrong payload is loud
at write time instead of a silently wrong cell in the UI.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from ..shared.errors import InvalidValueError

SCHEMA_VERSION = 1

MAX_ROWS = 40
MAX_REQUIREMENT = 240
MAX_EVIDENCE = 800
MAX_FIX = 500
MAX_VERDICT = 600
MAX_DOCUMENT_LABEL = 600  # cv_used / linkedin_used

KINDS = ("must", "nice")
MATCH_LEVELS = ("strong", "partial", "gap")
COVERAGE_LEVELS = ("shown", "partial", "missing", "na")
JD_SOURCES = ("full_text", "excerpt")

SUMMARY_KEYS = (
    "requirements", "must", "nice",
    "match_strong", "match_partial", "match_gap",
    "cv_shown", "cv_partial", "cv_missing",
    "linkedin_shown", "linkedin_partial", "linkedin_missing",
    "to_surface",
)

_DOCUMENTS = ("cv", "linkedin")
_NEEDS_WORK = ("partial", "missing")


def _text(value: Any, where: str, *, max_length: int) -> Optional[str]:
    """Optional free text: stripped, empty becomes None, over-long is an error."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidValueError(f"{where} must be a string")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise InvalidValueError(f"{where} is {len(text)} characters, the maximum is {max_length}")
    return text


def _choice(value: Any, where: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value.strip() not in allowed:
        raise InvalidValueError(f"{where} must be one of {', '.join(allowed)} (got {value!r})")
    return value.strip()


def _analyzed_on(value: Any, today: Optional[date]) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return (today or datetime.now(tz=timezone.utc).date()).isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            pass
    raise InvalidValueError(f"analyzed_on must be an ISO date (YYYY-MM-DD), got {value!r}")


def _jd_source(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _choice(value, "jd_source", JD_SOURCES)


def _match_block(row: dict[str, Any], where: str) -> dict[str, Any]:
    block = row.get("match")
    if not isinstance(block, dict):
        raise InvalidValueError(f"{where}.match is required: an object with level and evidence")
    evidence = _text(block.get("evidence"), f"{where}.match.evidence", max_length=MAX_EVIDENCE)
    if evidence is None:
        raise InvalidValueError(f"{where}.match.evidence is required: say why the level is what it is")
    return {"level": _choice(block.get("level"), f"{where}.match.level", MATCH_LEVELS), "evidence": evidence}


def _document_block(row: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    block = row.get(key)
    if not isinstance(block, dict):
        raise InvalidValueError(
            f'{where}.{key} is required: an object with a level (use {{"level": "na"}} when it does not apply)'
        )
    return {
        "level": _choice(block.get("level"), f"{where}.{key}.level", COVERAGE_LEVELS),
        "evidence": _text(block.get("evidence"), f"{where}.{key}.evidence", max_length=MAX_EVIDENCE),
        "fix": _text(block.get("fix"), f"{where}.{key}.fix", max_length=MAX_FIX),
    }


def _normalize_row(raw: Any, index: int) -> dict[str, Any]:
    where = f"rows[{index}]"
    if not isinstance(raw, dict):
        raise InvalidValueError(f"{where} must be an object")

    requirement = _text(raw.get("requirement"), f"{where}.requirement", max_length=MAX_REQUIREMENT)
    if requirement is None:
        raise InvalidValueError(f"{where}.requirement must be 1 to {MAX_REQUIREMENT} characters")

    kind = raw.get("kind")
    if kind is None or (isinstance(kind, str) and not kind.strip()):
        kind = "must"
    else:
        kind = _choice(kind, f"{where}.kind", KINDS)

    return {
        "requirement": requirement,
        "kind": kind,
        "match": _match_block(raw, where),
        "cv": _document_block(raw, "cv", where),
        "linkedin": _document_block(raw, "linkedin", where),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Counters over already-normalised rows. `na` coverage counts in no cv_* /
    linkedin_* bucket. `to_surface` is the actionable number: requirements Richard
    does meet (strong or partial) that at least one recruiter-facing document shows
    only partially or not at all."""
    summary = {key: 0 for key in SUMMARY_KEYS}
    summary["requirements"] = len(rows)
    for row in rows:
        summary[row["kind"]] += 1
        summary[f"match_{row['match']['level']}"] += 1
        for document in _DOCUMENTS:
            level = row[document]["level"]
            if level != "na":
                summary[f"{document}_{level}"] += 1
        if row["match"]["level"] in ("strong", "partial") and any(
            row[document]["level"] in _NEEDS_WORK for document in _DOCUMENTS
        ):
            summary["to_surface"] += 1
    return summary


def normalize_skill_match(raw: Any, *, today: Optional[date] = None) -> dict[str, Any]:
    """Validate a raw skill-match payload and return the shape that gets stored.

    `{}` / None are not valid here: clearing a role's skill match is the use case's
    decision, not a payload. `today` only exists so callers (tests) can pin the
    `analyzed_on` default; production leaves it unset and gets today's UTC date.
    """
    if not isinstance(raw, dict):
        raise InvalidValueError("skill_match must be an object")

    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise InvalidValueError(f"rows is required: a list of 1 to {MAX_ROWS} requirement rows")
    if len(raw_rows) > MAX_ROWS:
        raise InvalidValueError(f"rows has {len(raw_rows)} items, the maximum is {MAX_ROWS}")
    rows = [_normalize_row(row, index) for index, row in enumerate(raw_rows)]

    return {
        "version": SCHEMA_VERSION,
        "analyzed_on": _analyzed_on(raw.get("analyzed_on"), today),
        "verdict": _text(raw.get("verdict"), "verdict", max_length=MAX_VERDICT),
        "cv_used": _text(raw.get("cv_used"), "cv_used", max_length=MAX_DOCUMENT_LABEL),
        "linkedin_used": _text(raw.get("linkedin_used"), "linkedin_used", max_length=MAX_DOCUMENT_LABEL),
        "jd_source": _jd_source(raw.get("jd_source")),
        "rows": rows,
        "summary": summarize_rows(rows),
    }
