"""AttachSkillMatch use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import AttachSkillMatchCommand
from .response import AttachSkillMatchResponse


class IAttachSkillMatchUseCase(ABC):
    @abstractmethod
    async def execute(self, command: AttachSkillMatchCommand) -> AttachSkillMatchResponse: ...
