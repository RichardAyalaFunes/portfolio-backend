"""Shared role resolution for ingest-key endpoints that address one role by
`application_id` (preferred: the agent already holds it from a prior read or
publish) or by `jd_url`.

URL matching is the same two-step logic annotate and enrich_role use: the LinkedIn
job id extracted from `/jobs/view/<id>` or `currentJobId=<id>` against the
application id and every posting id, then exact string equality against `jd_url`
and every posting url. Those two use cases keep their own private copies (their
behaviour is pinned by the scripts that call them); new use cases import from here
instead of copying it a third time.
"""

import re
from typing import Optional

from backend.domain.applications.entities.job_application import JobApplication

_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(\d+)|currentJobId=(\d+)")

NO_IDENTIFIER = "(no identifier)"


def extract_linkedin_id(url: str) -> Optional[str]:
    match = _LINKEDIN_ID_RE.search(url)
    if not match:
        return None
    return match.group(1) or match.group(2)


def find_by_url(url: str, existing: list[JobApplication]) -> Optional[JobApplication]:
    candidate_id = extract_linkedin_id(url)
    if candidate_id:
        for application in existing:
            if str(application.id) == candidate_id or any(
                str(p.get("id")) == candidate_id for p in application.postings
            ):
                return application
    for application in existing:
        if application.jd_url == url or any(p.get("url") == url for p in application.postings):
            return application
    return None


def identifier_of(application_id: Optional[str], jd_url: Optional[str]) -> str:
    """What to echo back for an item in unmatched/invalid lists."""
    return application_id or jd_url or NO_IDENTIFIER


class RoleResolver:
    """Resolve batch items against one snapshot of the working set (built once per
    request, so a batch of N items costs one repository read)."""

    def __init__(self, existing: list[JobApplication]) -> None:
        self._existing = existing
        self._by_id = {str(application.id): application for application in existing}

    def resolve(self, *, application_id: Optional[str] = None, jd_url: Optional[str] = None) -> Optional[JobApplication]:
        """`application_id` first; when it is absent or unknown, fall back to `jd_url`."""
        if application_id:
            found = self._by_id.get(application_id.strip().lower())
            if found is not None:
                return found
        if jd_url:
            return find_by_url(jd_url, self._existing)
        return None
