"""FastAPI dependencies: container access, session check and CSRF check."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from vidgen.api.container import AppDeps, Container
from vidgen.api.errors import CSRF_FAILED, UNAUTHENTICATED, ApiError
from vidgen.api.security import (
    CSRF_HEADER,
    SAFE_METHODS,
    SESSION_COOKIE,
    Session,
    csrf_matches,
)

__all__ = ["AppDeps", "container", "require_csrf", "require_session"]


def container(request: Request) -> Container:
    """The container created by ``create_app``."""
    result: Container = request.app.state.container
    return result


def require_session(request: Request) -> Session:
    """401 unless the request carries a valid session cookie."""
    app = container(request)
    session = app.codec.read(request.cookies.get(SESSION_COOKIE), app.clock.now())
    if session is None:
        raise ApiError(401, UNAUTHENTICATED)
    return session


def require_csrf(request: Request, session: Annotated[Session, Depends(require_session)]) -> None:
    """403 for a state-changing request whose CSRF header does not match the session."""
    if request.method in SAFE_METHODS:
        return
    if not csrf_matches(session.csrf_token, request.headers.get(CSRF_HEADER)):
        raise ApiError(403, CSRF_FAILED)
