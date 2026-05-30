"""Speak use case — handler implementation."""

import base64

from .command import SpeakCommand
from .port import ISpeakUseCase
from .response import SpeakResponse
from ..ports.text_to_speech import ITextToSpeechClient


class SpeakHandler(ISpeakUseCase):
    """
    Synthesize text → PCM (via the TTS port) → base64 for transport.

    The frontend consumes the base64 directly: it chunks it (~1 s per
    `agent.speak` frame) and pushes through the WS bridge to LiveAvatar,
    which lip-syncs the avatar to the audio.
    """

    def __init__(self, tts_client: ITextToSpeechClient) -> None:
        self._tts = tts_client

    async def execute(self, command: SpeakCommand) -> SpeakResponse:
        text = command.text.strip()
        if not text:
            raise ValueError("text must be a non-empty string")

        audio = await self._tts.synthesize(text=text, voice=command.voice)

        return SpeakResponse(
            audio_b64=base64.b64encode(audio.pcm_bytes).decode("ascii"),
            sample_rate=audio.sample_rate,
            duration_ms=audio.duration_ms,
        )
