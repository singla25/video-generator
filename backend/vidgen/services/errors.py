"""Service-level exceptions. The API layer maps them to HTTP statuses."""

from __future__ import annotations

from vidgen.domain.codes import DomainError, FailureCode


class TemplateNotFoundError(Exception):
    """The requested template does not exist."""


class InvalidInputError(Exception):
    """A request value is missing or unusable (maps to VALIDATION_ERROR)."""


class PreconditionError(DomainError):
    """The action is not possible in the current state (maps to HTTP 409)."""

    def __init__(self, code: FailureCode) -> None:
        super().__init__(code)
