"""GetMetrics use case -- driver port (interface)."""

from abc import ABC, abstractmethod

from .command import GetMetricsCommand
from .response import MetricsResponse


class IGetMetricsUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetMetricsCommand) -> MetricsResponse: ...
