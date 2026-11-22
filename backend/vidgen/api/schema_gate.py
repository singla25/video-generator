"""Gate: while the database is behind the code, data routes answer one clear 503 (BL-8)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

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


def _relative_path(scope: Mapping[str, Any]) -> str:
    """Request path without the mount prefix.

    Under a Starlette ``Mount`` the path may still carry the mount (``root_path``), so the
    open-path check would never match behind the API prefix. Strip it only as a whole
    segment prefix; older Starlette versions already strip it, so both shapes work.
    """
    path: str = scope["path"]
    root: str = scope.get("root_path", "").rstrip("/")
    if root and (path == root or path.startswith(root + "/")):
        return path[len(root) :] or "/"
    return path


def _is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def install_schema_gate(app: FastAPI) -> None:
    """Add the gate middleware and the one start-up warning."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if app.state.container.schema is not None:
            warn_if_blocked(app.state.container.schema)
        yield

    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def gate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        check: SchemaCheck | None = request.app.state.container.schema
        if check is None or _is_open(_relative_path(request.scope)):
            return await call_next(request)
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
