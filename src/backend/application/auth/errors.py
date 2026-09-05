"""Auth application errors -- policy outcomes, not domain-entity invariants,
so they live alongside the use cases that raise them (mirrors how driven-adapter
errors like LiveAvatarHTTPError live next to the client that raises them)."""


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidPasswordError(AuthError):
    """The supplied password did not match DASHBOARD_PASSWORD."""


class AccountLockedError(AuthError):
    """Too many recent failed attempts for this IP or device."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Locked out; retry in at most {retry_after_seconds}s")


class InvalidTokenError(AuthError):
    """The device token is missing, malformed, expired, or wrongly signed."""
