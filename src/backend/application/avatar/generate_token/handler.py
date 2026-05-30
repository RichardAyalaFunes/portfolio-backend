"""GenerateToken use case — handler implementation."""

from .command import GenerateTokenCommand
from .port import IGenerateTokenUseCase
from .response import GenerateTokenResponse
from ..ports.avatar_api_client import IAvatarAPIClient


class GenerateTokenHandler(IGenerateTokenUseCase):
    """
    Orchestrates a LITE mode session token creation.

    Flow:
    1. Resolve avatar_id and is_sandbox from the command, falling back to settings defaults.
    2. Call IAvatarAPIClient.create_token (driven port) to request the LITE session.
    3. Return session_id + session_token to the controller.

    No persistence: the resulting token is short-lived and the frontend
    immediately calls /sessions/start with it to obtain LiveKit + ws_url.
    """

    def __init__(
        self,
        avatar_api_client: IAvatarAPIClient,
        default_avatar_id: str,
        default_voice_id: str,
        default_context_id: str,
        default_language: str,
        default_mode: str,
        default_is_sandbox: bool,
    ) -> None:
        self._client = avatar_api_client
        self._default_avatar_id = default_avatar_id
        self._default_voice_id = default_voice_id
        self._default_context_id = default_context_id
        self._default_language = default_language
        self._default_mode = default_mode
        self._default_is_sandbox = default_is_sandbox

    async def execute(self, command: GenerateTokenCommand) -> GenerateTokenResponse:
        avatar_id = command.avatar_id or self._default_avatar_id
        is_sandbox = (
            command.is_sandbox
            if command.is_sandbox is not None
            else self._default_is_sandbox
        )

        result = await self._client.create_token(
            avatar_id=avatar_id,
            voice_id=self._default_voice_id,
            context_id=self._default_context_id or None,
            language=self._default_language,
            mode=self._default_mode,
            is_sandbox=is_sandbox,
            max_session_duration=command.max_session_duration,
        )

        return GenerateTokenResponse(
            session_id=result.session_id,
            session_token=result.session_token,
        )
