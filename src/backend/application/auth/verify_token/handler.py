"""VerifyToken use case -- handler implementation.

No repository dependency -- HS256 verification is self-contained, same shape
as the token itself carries everything needed (mirrors how SpeakHandler in the
avatar context needs only its driven client, no persistence)."""

import jwt

from backend.application.auth.errors import InvalidTokenError

from .command import VerifyTokenCommand
from .port import IVerifyTokenUseCase
from .response import VerifyTokenResponse


class VerifyTokenHandler(IVerifyTokenUseCase):
    def __init__(self, token_secret: str) -> None:
        self._token_secret = token_secret

    async def execute(self, command: VerifyTokenCommand) -> VerifyTokenResponse:
        try:
            payload = jwt.decode(command.token, self._token_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        device_id = payload.get("device_id")
        if not device_id:
            raise InvalidTokenError("token missing device_id claim")
        return VerifyTokenResponse(device_id=device_id)
