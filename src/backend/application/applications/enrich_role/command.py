"""EnrichRole use case -- command DTO. Mirrors enrich.js's per-role blocks.

Each item identifies a role by `application_id` (preferred -- the agent already
has it from a prior read/publish) or falls back to `jd_url` matching, the same
way annotate.js does. `contacts` and `application_form` are each optional and
independent: an item may update only one of the two. Omitting a field means
"leave it alone", not "clear it" -- to actually clear one, send an empty list/dict.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class EnrichRoleItem:
    application_id: Optional[str] = None
    jd_url: Optional[str] = None
    contacts: Optional[list[dict[str, Any]]] = None
    application_form: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class EnrichRoleCommand:
    items: list[EnrichRoleItem]
