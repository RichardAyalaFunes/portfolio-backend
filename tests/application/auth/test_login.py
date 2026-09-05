"""LoginHandler tests against a fake in-memory ILoginAttemptRepository -- no network."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.application.auth.errors import AccountLockedError, InvalidPasswordError
from backend.application.auth.login.command import LoginCommand
from backend.application.auth.login.handler import LoginHandler
from backend.application.auth.ports.login_attempt_repository import ILoginAttemptRepository

PASSWORD = "correct-horse"
SECRET = "test-secret"


class FakeAttemptRepository(ILoginAttemptRepository):
    def __init__(self) -> None:
        self.attempts: list[dict] = []

    async def record(self, *, ip, device_id, success) -> None:
        self.attempts.append({"ip": ip, "device_id": device_id, "success": success, "at": datetime.now(tz=timezone.utc)})

    async def count_recent_failures(self, *, ip, device_id, since) -> int:
        return sum(
            1
            for a in self.attempts
            if not a["success"] and a["at"] >= since and (a["device_id"] == device_id or a["ip"] == ip)
        )


def make_handler(repo: FakeAttemptRepository, max_attempts: int = 10) -> LoginHandler:
    return LoginHandler(
        attempt_repository=repo,
        dashboard_password=PASSWORD,
        token_secret=SECRET,
        token_days=30,
        max_attempts=max_attempts,
        lock_hours=24,
    )


@pytest.mark.asyncio
async def test_correct_password_issues_a_valid_token():
    handler = make_handler(FakeAttemptRepository())
    result = await handler.execute(LoginCommand(password=PASSWORD, device_id="dev-1", ip="1.2.3.4"))

    payload = jwt.decode(result.token, SECRET, algorithms=["HS256"])
    assert payload["device_id"] == "dev-1"
    assert result.expires_at > datetime.now(tz=timezone.utc) + timedelta(days=29)


@pytest.mark.asyncio
async def test_wrong_password_raises_and_records_failure():
    repo = FakeAttemptRepository()
    handler = make_handler(repo)

    with pytest.raises(InvalidPasswordError):
        await handler.execute(LoginCommand(password="nope", device_id="dev-1", ip="1.2.3.4"))

    assert len(repo.attempts) == 1
    assert repo.attempts[0]["success"] is False


@pytest.mark.asyncio
async def test_lockout_after_max_attempts_blocks_even_the_correct_password():
    repo = FakeAttemptRepository()
    handler = make_handler(repo, max_attempts=3)

    for _ in range(3):
        with pytest.raises(InvalidPasswordError):
            await handler.execute(LoginCommand(password="nope", device_id="dev-1", ip="1.2.3.4"))

    with pytest.raises(AccountLockedError):
        await handler.execute(LoginCommand(password=PASSWORD, device_id="dev-1", ip="1.2.3.4"))


@pytest.mark.asyncio
async def test_lockout_is_scoped_by_device_or_ip_not_global():
    repo = FakeAttemptRepository()
    handler = make_handler(repo, max_attempts=3)

    for _ in range(3):
        with pytest.raises(InvalidPasswordError):
            await handler.execute(LoginCommand(password="nope", device_id="dev-1", ip="1.2.3.4"))

    # A different device from a different IP is unaffected.
    result = await handler.execute(LoginCommand(password=PASSWORD, device_id="dev-2", ip="9.9.9.9"))
    assert result.token
