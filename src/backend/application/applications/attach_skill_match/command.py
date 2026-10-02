"""AttachSkillMatch use case -- command DTO.

Each item identifies a role by `application_id` (preferred) or falls back to `jd_url`
matching, the same way enrich_role does, and carries that role's whole skill-match
table. `skill_match` None (or an empty dict) clears the role's table; anything else
is a raw payload the handler validates and normalises -- see
domain.applications.skill_match for the accepted shape.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AttachSkillMatchItem:
    application_id: Optional[str] = None
    jd_url: Optional[str] = None
    # Whatever the agent sent: an object, None/{} to clear, or garbage the handler reports.
    skill_match: Any = None


@dataclass(frozen=True)
class AttachSkillMatchCommand:
    items: list[AttachSkillMatchItem]
