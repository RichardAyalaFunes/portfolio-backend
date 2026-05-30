"""GenerateToken use case — command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GenerateTokenCommand:
    """
    Command to create a new LiveAvatar LITE mode session.

    avatar_id:            Override the default avatar from settings.
    max_session_duration: Session lifetime in seconds (max 3600).
    is_sandbox:           None means "use the settings default".
    """

    avatar_id: Optional[str] = None
    max_session_duration: int = 120
    is_sandbox: Optional[bool] = None
