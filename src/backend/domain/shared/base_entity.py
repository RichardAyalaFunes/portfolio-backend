"""Base Entity and AggregateRoot — identity-based equality with domain event support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

ID = TypeVar("ID")


@dataclass
class Entity(Generic[ID]):
    """
    Base entity with identity-based equality.

    Two entities are equal if and only if their IDs match.
    """

    id: ID

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id  # type: ignore[union-attr]

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class AggregateRoot(Entity[ID]):
    """
    Aggregate root — boundary of a consistency unit.

    Collects domain events during business operations;
    callers are responsible for dispatching/clearing them.
    """

    _domain_events: list = field(default_factory=list, init=False, repr=False, compare=False)

    def add_domain_event(self, event: object) -> None:
        """Record a domain event raised by this aggregate."""
        self._domain_events.append(event)

    def pull_domain_events(self) -> list:
        """Return and clear all pending domain events."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
