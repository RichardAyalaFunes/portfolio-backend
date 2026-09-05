"""VerifyToken use case -- command DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifyTokenCommand:
    token: str
