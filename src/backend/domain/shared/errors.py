"""Domain exceptions — pure Python, no framework dependencies."""


class DomainError(Exception):
    """Base class for domain-level invariant violations."""


class NotFoundError(DomainError):
    """Raised when an aggregate or entity is not found."""


class InvalidValueError(DomainError):
    """Raised when a value object receives an invalid value."""


class SessionExpiredError(DomainError):
    """Raised when an avatar session has expired."""


class InvalidStateTransitionError(DomainError):
    """Raised when an invalid state transition is attempted."""
