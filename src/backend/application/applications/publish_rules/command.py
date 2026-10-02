"""PublishRules use case -- command DTO.

`content` is the search-rules document the job-search agent publishes. The backend
treats it as opaque JSON and only sanity-checks the handful of keys the dashboard
needs to render it (see handler.validate_rules); the agent's own config stays the
source of truth for everything else in it.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublishRulesCommand:
    content: dict[str, Any]
