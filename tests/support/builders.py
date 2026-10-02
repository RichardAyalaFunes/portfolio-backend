"""Small builders shared by the dashboard tests: a JobApplication with sensible
defaults, and a valid raw skill-match payload (the shape the agent sends)."""

from __future__ import annotations

import itertools
from typing import Any, Optional

from backend.domain.applications.entities.job_application import JobApplication
from backend.domain.applications.value_objects import ApplicationId

_counter = itertools.count(1)


def make_application(**overrides: Any) -> JobApplication:
    """A JobApplication with a fresh id and its own identity_key; override any field."""
    n = next(_counter)
    fields: dict[str, Any] = {
        "id": ApplicationId.generate(),
        "identity_key": f"company {n}::engineer {n}",
        "title": f"Engineer {n}",
        "company": f"Company {n}",
    }
    fields.update(overrides)
    return JobApplication(**fields)


def skill_match_row(
    requirement: str = "Python, typed and tested; FastAPI",
    *,
    kind: str = "must",
    match: str = "strong",
    cv: str = "shown",
    linkedin: str = "shown",
    cv_fix: Optional[str] = None,
    linkedin_fix: Optional[str] = None,
) -> dict[str, Any]:
    """One raw requirement row, as the agent would send it. Levels are plain strings."""
    return {
        "requirement": requirement,
        "kind": kind,
        "match": {"level": match, "evidence": f"Evidence for: {requirement}"},
        "cv": {"level": cv, "evidence": None, "fix": cv_fix},
        "linkedin": {"level": linkedin, "evidence": None, "fix": linkedin_fix},
    }


def skill_match_payload(**overrides: Any) -> dict[str, Any]:
    """A valid raw payload with two rows: one worth surfacing, one gap."""
    payload: dict[str, Any] = {
        "analyzed_on": "2026-10-01",
        "verdict": "Strong technical fit; LinkedIn does not show FastAPI yet.",
        "cv_used": "demo-cv.pdf",
        "linkedin_used": "demo LinkedIn snapshot",
        "jd_source": "full_text",
        "rows": [
            skill_match_row(linkedin="partial", linkedin_fix="Add FastAPI to the Skills list."),
            skill_match_row("Kubernetes in production", kind="nice", match="gap", cv="na", linkedin="na"),
        ],
    }
    payload.update(overrides)
    return payload
