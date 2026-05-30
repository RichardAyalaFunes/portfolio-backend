"""
ITextToSpeechClient — driven port for text-to-speech synthesis.

The application layer depends only on this interface; the concrete
adapter (e.g. OpenAITTSClient) lives in infrastructure. This keeps
the speak use case provider-agnostic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SynthesizedAudio:
    """
    Raw synthesized audio result.

    pcm_bytes:    Linear PCM, signed 16-bit, little-endian, mono.
    sample_rate:  Sample rate in Hz. LiveAvatar requires exactly 24000.
    """

    pcm_bytes: bytes
    sample_rate: int

    @property
    def duration_ms(self) -> int:
        """Duration of the audio in milliseconds (16-bit mono PCM = 2 bytes/frame)."""
        if self.sample_rate <= 0:
            return 0
        return int(len(self.pcm_bytes) / 2 / self.sample_rate * 1000)


class ITextToSpeechClient(ABC):
    """Driven port — synthesize text into LiveAvatar-compatible PCM audio."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> SynthesizedAudio:
        """
        Convert `text` into 16-bit / 24 kHz / mono PCM audio.

        `voice` is provider-specific (e.g., OpenAI: alloy/echo/fable/onyx/nova/shimmer).
        Pass None to use the adapter's default.
        """
