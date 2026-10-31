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


class TemplateInUseError(Exception):
    """The template is used by batches, so it cannot be deleted (maps to HTTP 409)."""

    CODE = "TEMPLATE_IN_USE"

    def __init__(self, batches: int) -> None:
        self.code = self.CODE
        noun = "batch" if batches == 1 else "batches"
        self.message = f"This template is used by {batches} {noun}. Delete those batches first."
        super().__init__(self.message)


class BatchNotFoundError(TemplateNotFoundError):
    """The requested batch (or row, or file) does not exist."""


class StateConflictError(Exception):
    """The action does not fit the batch's current state (maps to HTTP 409)."""

    INVALID_STATE = "INVALID_STATE"
    PREVIEW_NOT_READY = "PREVIEW_NOT_READY"
    PREVIEW_NOT_APPROVED = "PREVIEW_NOT_APPROVED"
    SPELLING_NOT_CONFIRMED = "SPELLING_NOT_CONFIRMED"

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
