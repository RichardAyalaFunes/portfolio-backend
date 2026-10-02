"""GetRules use case -- command DTO. No parameters: there is one published document."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetRulesCommand:
    pass
