"""GetFeedback use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetFeedbackCommand
from .response import FeedbackResponse


class IGetFeedbackUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetFeedbackCommand) -> FeedbackResponse: ...
