"""VerifyToken use case -- response DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifyTokenResponse:
    device_id: str
