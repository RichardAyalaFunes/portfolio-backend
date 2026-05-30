"""Base ValueObject — immutable, equality by attributes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueObject:
    """
    Marker base class for value objects.

    - Equality is structural (all fields must match).
    - Instances are immutable (frozen dataclass).
    - No identity concept; two VOs with the same data are equal.
    """
