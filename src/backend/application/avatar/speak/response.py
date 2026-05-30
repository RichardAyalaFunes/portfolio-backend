"""Speak use case — response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeakResponse:
    """
    Result of the Speak use case.

    audio_b64:    Base64-encoded PCM 16-bit / mono audio, ready to put in
                  the `audio` field of a LiveAvatar `agent.speak` WS event.
    sample_rate:  24000 (LiveAvatar's required rate; OpenAI's `pcm` format).
    duration_ms:  Approximate playback length, useful for client pacing.
    """

    audio_b64: str
    sample_rate: int
    duration_ms: int
