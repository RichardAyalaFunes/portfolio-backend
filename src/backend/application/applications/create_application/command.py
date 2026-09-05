"""CreateApplication use case -- command DTO."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateApplicationCommand:
    title: str
    company: str
    group: Optional[str] = None
    jd_url: Optional[str] = None
    status: str = "To validate"
