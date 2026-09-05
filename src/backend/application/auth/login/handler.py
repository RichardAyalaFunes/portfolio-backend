"""Login use case -- handler implementation.

Flow: check lockout first (regardless of password correctness -- once locked,
even the right password waits it out, matching the approved MVP design), then
constant-effort password compare, recording every attempt either way.
"""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from backend.application.auth.errors import AccountLockedError, InvalidPasswordError
from backend.application.auth.ports.login_attempt_repository import ILoginAttemptRepository

from .command import LoginCommand
from .port import ILoginUseCase
from .response import LoginResponse

_WRONG_PASSWORD_DELAY_SECONDS = 0.5


class LoginHandler(ILoginUseCase):
    def __init__(
        self,
        attempt_repository: ILoginAttemptRepository,
        dashboard_password: str,
        token_secret: str,
        token_days: int,
        max_attempts: int,
        lock_hours: int,
    ) -> None:
        self._attempts = attempt_repository
        self._password = dashboard_password
        self._token_secret = token_secret
        self._token_days = token_days
        self._max_attempts = max_attempts
        self._lock_hours = lock_hours

    async def execute(self, command: LoginCommand) -> LoginResponse:
        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(hours=self._lock_hours)

        failures = await self._attempts.count_recent_failures(
            ip=command.ip, device_id=command.device_id, since=since
        )
        if failures >= self._max_attempts:
            raise AccountLockedError(retry_after_seconds=self._lock_hours * 3600)

        if not secrets.compare_digest(command.password, self._password):
            await self._attempts.record(ip=command.ip, device_id=command.device_id, success=False)
            await asyncio.sleep(_WRONG_PASSWORD_DELAY_SECONDS)
            raise InvalidPasswordError()

        await self._attempts.record(ip=command.ip, device_id=command.device_id, success=True)

        expires_at = now + timedelta(days=self._token_days)
        token = jwt.encode(
            {"device_id": command.device_id, "iat": now, "exp": expires_at},
            self._token_secret,
            algorithm="HS256",
        )
        return LoginResponse(token=token, expires_at=expires_at)
