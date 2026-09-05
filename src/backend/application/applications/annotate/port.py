"""Annotate use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import AnnotateCommand
from .response import AnnotateResponse


class IAnnotateUseCase(ABC):
    @abstractmethod
    async def execute(self, command: AnnotateCommand) -> AnnotateResponse: ...
