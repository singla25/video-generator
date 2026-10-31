"""JSON error bodies ``{code, message}`` and the handlers that produce them.

Messages are fixed plain-language texts. Nothing from the request, from exception text or from
a stack trace is ever echoed back (C5).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from vidgen.domain.codes import DomainError, FailureCode, plain_message
from vidgen.services.errors import (
    InvalidInputError,
    PreconditionError,
    StateConflictError,
    TemplateInUseError,
    TemplateNotFoundError,
)

logger = logging.getLogger(__name__)

UNAUTHENTICATED = "UNAUTHENTICATED"
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
CSRF_FAILED = "CSRF_FAILED"
RATE_LIMITED = "RATE_LIMITED"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
INVALID_STATE = "INVALID_STATE"
PREVIEW_NOT_READY = "PREVIEW_NOT_READY"
PREVIEW_NOT_APPROVED = "PREVIEW_NOT_APPROVED"
SPELLING_NOT_CONFIRMED = "SPELLING_NOT_CONFIRMED"
TEMPLATE_IN_USE = "TEMPLATE_IN_USE"
DB_UNAVAILABLE = "DB_UNAVAILABLE"
QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
HTTP_UNAVAILABLE = 503

API_MESSAGES: Mapping[str, str] = {
    UNAUTHENTICATED: "Please log in to continue.",
    INVALID_CREDENTIALS: "The password is not correct.",
    CSRF_FAILED: "The request could not be verified. Reload the page and try again.",
    RATE_LIMITED: "Too many attempts. Please wait a little and try again.",
    NOT_FOUND: "The requested item was not found.",
    VALIDATION_ERROR: "The request is missing something or has an invalid value.",
    METHOD_NOT_ALLOWED: "This action is not available here.",
    INVALID_STATE: "This action is not possible in the batch's current state.",
    PREVIEW_NOT_READY: "The preview is not ready for the current settings yet.",
    PREVIEW_NOT_APPROVED: "Approve a preview of the current settings before starting.",
    SPELLING_NOT_CONFIRMED: "Confirm the spelling of the spoken name before approving the preview.",
    DB_UNAVAILABLE: "The database is not reachable right now. Please try again in a moment.",
    QUEUE_UNAVAILABLE: "The job queue is not reachable right now. Please try again in a moment.",
}

HTTP_UNPROCESSABLE = 422
STATUS_BY_CODE: Mapping[FailureCode, int] = {
    FailureCode.STORAGE_ERROR: 507,
    FailureCode.STT_FAILED: 502,
    FailureCode.INTERNAL_ERROR: 500,
    FailureCode.NO_COMPLETED_ROWS: 409,
    FailureCode.IDEMPOTENCY_KEY_CONFLICT: 409,
}


class ApiError(Exception):
    """An error with an explicit HTTP status, API code and plain message."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message if message is not None else API_MESSAGES[code]
        self.headers = dict(headers or {})
        super().__init__(self.message)


def error_response(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    """The one error body shape."""
    return JSONResponse(
        {"code": code, "message": message}, status_code=status, headers=dict(headers or {})
    )


def _api_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(ApiError, exc)
    return error_response(error.status, error.code, error.message, error.headers)


def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(DomainError, exc)
    if isinstance(error, PreconditionError):
        status = 409
    else:
        status = STATUS_BY_CODE.get(error.code, HTTP_UNPROCESSABLE)
    return error_response(status, error.code.value, error.message)


def _state_conflict(_: Request, exc: Exception) -> JSONResponse:
    error = cast(StateConflictError, exc)
    return error_response(409, error.code, API_MESSAGES[error.code])


def _template_in_use(_: Request, exc: Exception) -> JSONResponse:
    error = cast(TemplateInUseError, exc)
    return error_response(409, error.code, error.message)


def _not_found(_: Request, __: Exception) -> JSONResponse:
    return error_response(404, NOT_FOUND, API_MESSAGES[NOT_FOUND])


def _invalid_input(_: Request, __: Exception) -> JSONResponse:
    return error_response(HTTP_UNPROCESSABLE, VALIDATION_ERROR, API_MESSAGES[VALIDATION_ERROR])


def _http_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    if error.status_code == 405:
        return error_response(405, METHOD_NOT_ALLOWED, API_MESSAGES[METHOD_NOT_ALLOWED])
    if error.status_code == 404:
        return error_response(404, NOT_FOUND, API_MESSAGES[NOT_FOUND])
    return error_response(error.status_code, VALIDATION_ERROR, API_MESSAGES[VALIDATION_ERROR])


def _unavailable(code: str, exc: Exception) -> JSONResponse:
    # Only the type is logged: the text can hold the connection string with its password.
    logger.error("dependency unavailable", extra={"error_type": type(exc).__name__, "code": code})
    return error_response(HTTP_UNAVAILABLE, code, API_MESSAGES[code])


def _db_unavailable(_: Request, exc: Exception) -> JSONResponse:
    return _unavailable(DB_UNAVAILABLE, exc)


def _queue_unavailable(_: Request, exc: Exception) -> JSONResponse:
    return _unavailable(QUEUE_UNAVAILABLE, exc)


def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    # Only the type is logged: the text may contain names or IDs (C5).
    logger.error("unhandled error", extra={"error_type": type(exc).__name__})
    code = FailureCode.INTERNAL_ERROR
    return error_response(500, code.value, plain_message(code))


def install_error_handlers(app: FastAPI) -> None:
    """Register every handler on the app."""
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(StateConflictError, _state_conflict)
    app.add_exception_handler(TemplateNotFoundError, _not_found)
    app.add_exception_handler(TemplateInUseError, _template_in_use)
    app.add_exception_handler(InvalidInputError, _invalid_input)
    app.add_exception_handler(RequestValidationError, _invalid_input)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(OperationalError, _db_unavailable)
    app.add_exception_handler(InterfaceError, _db_unavailable)
    app.add_exception_handler(PoolTimeoutError, _db_unavailable)
    app.add_exception_handler(RedisError, _queue_unavailable)
    app.add_exception_handler(ConnectionRefusedError, _queue_unavailable)
    app.add_exception_handler(Exception, _unexpected)
