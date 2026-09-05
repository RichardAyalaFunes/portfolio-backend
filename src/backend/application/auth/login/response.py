"""Login use case -- response DTO."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LoginResponse:
    token: str
    expires_at: datetime
