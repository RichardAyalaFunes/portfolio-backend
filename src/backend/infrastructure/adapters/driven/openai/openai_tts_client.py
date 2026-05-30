"""
OpenAITTSClient — driven adapter implementing ITextToSpeechClient.

Calls OpenAI's text-to-speech API and returns raw 16-bit / 24 kHz / mono
PCM, which matches LiveAvatar's `agent.speak` audio requirement exactly
(`response_format="pcm"` is documented as 24 kHz signed 16-bit little-endian).

The AsyncOpenAI client is constructed by the FastAPI lifespan and shared
across requests (it owns its own httpx pool).
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI, OpenAIError

from backend.application.avatar.ports.text_to_speech import (
    ITextToSpeechClient,
    SynthesizedAudio,
)

logger = logging.getLogger(__name__)

# OpenAI's `response_format="pcm"` is documented as 24 kHz, signed 16-bit
# little-endian, mono. This MUST match LiveAvatar's expected agent.speak format.
_OPENAI_PCM_SAMPLE_RATE = 24_000


class OpenAITTSError(Exception):
    """Raised when the OpenAI TTS call fails."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class OpenAITTSClient(ITextToSpeechClient):
    def __init__(
        self,
        client: AsyncOpenAI,
        default_model: str = "tts-1",
        default_voice: str = "alloy",
    ) -> None:
        self._client = client
        self._default_model = default_model
        self._default_voice = default_voice

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
    ) -> SynthesizedAudio:
        chosen_voice = voice or self._default_voice

        try:
            response = await self._client.audio.speech.create(
                model=self._default_model,
                voice=chosen_voice,
                input=text,
                response_format="pcm",  # 24 kHz, 16-bit, mono — LiveAvatar's required format
            )
            audio_bytes = await response.aread()
        except OpenAIError as exc:
            # Surface a sanitized message; the controller maps this to 502.
            logger.exception("OpenAI TTS request failed")
            raise OpenAITTSError(str(exc)) from exc

        logger.info(
            "OpenAI TTS synthesized %d bytes (~%d ms) voice=%s model=%s",
            len(audio_bytes),
            int(len(audio_bytes) / 2 / _OPENAI_PCM_SAMPLE_RATE * 1000),
            chosen_voice,
            self._default_model,
        )

        return SynthesizedAudio(
            pcm_bytes=audio_bytes,
            sample_rate=_OPENAI_PCM_SAMPLE_RATE,
        )
