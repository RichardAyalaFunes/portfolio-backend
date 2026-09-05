"""ApplyLiveness use case -- command DTO. `sweep` mirrors apply-liveness.js's
input shape: {posting_id: {state, remote, url}}."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApplyLivenessCommand:
    sweep: dict[str, dict[str, Any]]
