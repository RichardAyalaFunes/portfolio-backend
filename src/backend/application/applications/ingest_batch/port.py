"""IngestBatch use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import IngestBatchCommand
from .response import IngestBatchResponse


class IIngestBatchUseCase(ABC):
    @abstractmethod
    async def execute(self, command: IngestBatchCommand) -> IngestBatchResponse: ...
