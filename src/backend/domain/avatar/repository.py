"""Avatar domain driven port — repository interface."""

from abc import ABC, abstractmethod
from typing import Optional

from .entities.avatar_session import AvatarSession
from .value_objects import AvatarSessionId, LiveAvatarSessionId


class IAvatarSessionRepository(ABC):
    """Repository interface (driven port) for the AvatarSession aggregate."""

    @abstractmethod
    async def find_by_id(self, session_id: AvatarSessionId) -> Optional[AvatarSession]: ...

    @abstractmethod
    async def find_by_liveavatar_session_id(
        self, liveavatar_session_id: LiveAvatarSessionId
    ) -> Optional[AvatarSession]: ...

    @abstractmethod
    async def save(self, session: AvatarSession) -> None: ...

    @abstractmethod
    async def delete(self, session: AvatarSession) -> None: ...
