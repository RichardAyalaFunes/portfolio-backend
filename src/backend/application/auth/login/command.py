"""Login use case -- command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LoginCommand:
    password: str
    device_id: str
    ip: Optional[str] = None
