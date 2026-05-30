"""AvatarSession aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ...shared.base_entity import AggregateRoot
from ...shared.errors import InvalidStateTransitionError, SessionExpiredError
from ..value_objects import AvatarSessionId, AvatarState, LiveAvatarSessionId, SessionToken

# Valid state transitions
_ALLOWED_TRANSITIONS: dict[AvatarState, set[AvatarState]] = {
    AvatarState.CONNECTING: {AvatarState.IDLE, AvatarState.CLOSED},
    AvatarState.IDLE: {AvatarState.LISTENING, AvatarState.SPEAKING, AvatarState.CLOSED},
    AvatarState.LISTENING: {AvatarState.THINKING, AvatarState.IDLE, AvatarState.CLOSED},
    AvatarState.THINKING: {AvatarState.SPEAKING, AvatarState.IDLE, AvatarState.CLOSED},
    AvatarState.SPEAKING: {AvatarState.IDLE, AvatarState.LISTENING, AvatarState.CLOSED},
    AvatarState.CLOSED: set(),
}


@dataclass
class AvatarSession(AggregateRoot[AvatarSessionId]):
    """
    Aggregate root for a LiveAvatar LITE mode session.

    Invariants:
    - Token must be non-empty
    - expires_at must be in the future when commanding the avatar
    - State transitions must follow the allowed graph
    - Sessions cannot be commanded after expiry or closure
    """

    liveavatar_session_id: LiveAvatarSessionId
    token: SessionToken
    expires_at: datetime
    ws_url: Optional[str] = None
    state: AvatarState = field(default=AvatarState.CONNECTING)

    # Max 2-hour sessions per architecture doc
    MAX_DURATION_SECONDS: int = field(default=7200, init=False, repr=False, compare=False)

    @staticmethod
    def create(
        liveavatar_session_id: str,
        token: str,
        expires_at: datetime,
        ws_url: Optional[str] = None,
    ) -> "AvatarSession":
        """Factory method — called after the LiveAvatar API returns a token."""
        return AvatarSession(
            id=AvatarSessionId.generate(),
            liveavatar_session_id=LiveAvatarSessionId.from_string(liveavatar_session_id),
            token=SessionToken.from_string(token),
            expires_at=expires_at,
            ws_url=ws_url,
            state=AvatarState.CONNECTING,
        )

    def transition_to(self, new_state: AvatarState) -> None:
        """Validate and apply a state transition."""
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition from {self.state} to {new_state}"
            )
        self.state = new_state

    def close(self) -> None:
        """Mark the session as closed (terminal state)."""
        self.state = AvatarState.CLOSED

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=timezone.utc) >= self.expires_at

    @property
    def is_active(self) -> bool:
        return self.state != AvatarState.CLOSED and not self.is_expired

    @property
    def time_remaining_seconds(self) -> int:
        if self.is_expired:
            return 0
        delta = self.expires_at - datetime.now(tz=timezone.utc)
        return max(0, int(delta.total_seconds()))

    def assert_commandable(self) -> None:
        """Raise if the session cannot accept commands."""
        if self.is_expired:
            raise SessionExpiredError(
                f"Session {self.liveavatar_session_id.value} has expired"
            )
        if self.state == AvatarState.CLOSED:
            raise SessionExpiredError(
                f"Session {self.liveavatar_session_id.value} is already closed"
            )
