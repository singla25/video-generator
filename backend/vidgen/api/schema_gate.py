"""Gate: while the database is behind the code, data routes answer one clear 503 (BL-8)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from vidgen.api.errors import API_MESSAGES, DB_UNAVAILABLE, HTTP_UNAVAILABLE, error_response
from vidgen.services.schema_check import SchemaCheck

logger = logging.getLogger(__name__)

DB_NEEDS_MIGRATION = "DB_NEEDS_MIGRATION"
OPEN_PATHS = ("/health", "/system/status")
OPEN_PREFIXES = ("/auth/",)
DB_ERRORS = (OperationalError, InterfaceError, PoolTimeoutError)


def _is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def install_schema_gate(app: FastAPI) -> None:
    """Add the gate middleware and the one start-up warning."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        warn_if_blocked(app.state.container.schema)
        yield

    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def gate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if _is_open(request.url.path):
            return await call_next(request)
        check: SchemaCheck = request.app.state.container.schema
        try:
            status = check.status()
        except DB_ERRORS as exc:
            # Only the type is logged: the text can hold the connection string.
            logger.error("schema check failed", extra={"error_type": type(exc).__name__})
            return error_response(HTTP_UNAVAILABLE, DB_UNAVAILABLE, API_MESSAGES[DB_UNAVAILABLE])
        if status.blocks:
            return error_response(HTTP_UNAVAILABLE, DB_NEEDS_MIGRATION, status.message)
        return await call_next(request)


def warn_if_blocked(check: SchemaCheck) -> None:
    """Log one WARNING at start when the schema is behind; a down database is only noted."""
    try:
        status = check.status()
    except DB_ERRORS as exc:
        logger.warning("schema check skipped", extra={"error_type": type(exc).__name__})
        return
    if status.blocks:
        logger.warning(status.message, extra={"schema_state": status.state.value})
