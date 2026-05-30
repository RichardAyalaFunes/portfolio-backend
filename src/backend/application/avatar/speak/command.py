"""Speak use case — command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SpeakCommand:
    """
    Command to synthesize text into LiveAvatar-ready PCM audio.

    text:  The line the avatar should speak. Must be non-empty.
    voice: Optional override of the configured default TTS voice.
    """

    text: str
    voice: Optional[str] = None
