"""Avatar domain — value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from ..shared.base_value_object import ValueObject
from ..shared.errors import InvalidValueError


@dataclass(frozen=True)
class AvatarSessionId(ValueObject):
    """Unique identifier for an AvatarSession aggregate."""

    value: str

    @staticmethod
    def generate() -> "AvatarSessionId":
        return AvatarSessionId(value=f"avtr_{uuid4()}")

    @staticmethod
    def from_string(value: str) -> "AvatarSessionId":
        if not value:
            raise InvalidValueError("AvatarSessionId cannot be empty")
        return AvatarSessionId(value=value)


@dataclass(frozen=True)
class LiveAvatarSessionId(ValueObject):
    """Session ID returned by the LiveAvatar API (external reference)."""

    value: str

    @staticmethod
    def from_string(value: str) -> "LiveAvatarSessionId":
        if not value:
            raise InvalidValueError("LiveAvatarSessionId cannot be empty")
        return LiveAvatarSessionId(value=value)


@dataclass(frozen=True)
class SessionToken(ValueObject):
    """
    Short-lived WebRTC session token issued by LiveAvatar.

    This token is sent to the frontend SDK to establish the WebRTC
    connection. It must never be logged or stored long-term.
    """

    value: str

    @staticmethod
    def from_string(value: str) -> "SessionToken":
        if not value:
            raise InvalidValueError("SessionToken cannot be empty")
        return SessionToken(value=value)


class AvatarState(str, Enum):
    """States the avatar can be in during a session."""

    CONNECTING = "connecting"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CLOSED = "closed"

    @property
    def is_active(self) -> bool:
        return self not in (AvatarState.CONNECTING, AvatarState.CLOSED)
