"""Applications bounded-context application errors."""


class ApplicationError(Exception):
    """Base class for applications-bounded-context application failures."""


class DuplicateApplicationError(ApplicationError):
    """A manual add matched an existing application via identity matching."""

    def __init__(self, existing_id: str) -> None:
        self.existing_id = existing_id
        super().__init__(f"Matches existing application {existing_id}")
