"""AttachSkillMatch use case -- response DTO.

matched:   items that resolved to a role (whatever became of their payload).
updated:   matched items whose table was written (stored, or cleared).
unmatched: identifiers that resolved to no role.
invalid:   "<identifier>: <reason>" for matched items whose payload failed
           validation; they were skipped and the rest of the batch still applied.
So matched == updated + len(invalid).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttachSkillMatchResponse:
    matched: int
    updated: int
    unmatched: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
