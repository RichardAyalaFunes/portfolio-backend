"""CreateRealtimeSession use case — handler implementation."""

from .command import CreateRealtimeSessionCommand
from .port import ICreateRealtimeSessionUseCase
from .response import CreateRealtimeSessionResponse
from ..ports.realtime_api_client import IRealtimeAPIClient


class CreateRealtimeSessionHandler(ICreateRealtimeSessionUseCase):
    """
    Mints an OpenAI Realtime ephemeral key so the browser can open
    a WebRTC connection directly to OpenAI without exposing the
    master API key.
    """

    def __init__(
        self,
        realtime_client: IRealtimeAPIClient,
        default_model: str,
        default_voice: str,
    ) -> None:
        self._client = realtime_client
        self._default_model = default_model
        self._default_voice = default_voice

    async def execute(
        self, command: CreateRealtimeSessionCommand
    ) -> CreateRealtimeSessionResponse:
        voice = command.voice or self._default_voice

        result = await self._client.create_ephemeral_session(
            model=self._default_model,
            voice=voice,
        )

        return CreateRealtimeSessionResponse(
            client_secret=result.client_secret,
            expires_at=result.expires_at,
        )
