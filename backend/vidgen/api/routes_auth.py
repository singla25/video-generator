"""Login and logout (ADR-006, D-15)."""

from __future__ import annotations

from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from vidgen.api.client_address import resolve_client_address
from vidgen.api.container import Container
from vidgen.api.deps import container, require_csrf
from vidgen.api.errors import INVALID_CREDENTIALS, RATE_LIMITED, ApiError
from vidgen.api.schemas import LoginRequest
from vidgen.api.security import CSRF_COOKIE, SESSION_COOKIE
from vidgen.services.audit import ACTOR_ADMIN, ACTOR_ANONYMOUS, ACTOR_SYSTEM

open_router = APIRouter(prefix="/auth", tags=["auth"])
protected_router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_csrf)])
UNKNOWN_PEER = "unknown"


def _password_ok(app: Container, password: str) -> bool:
    """Verify against the configured argon2 hash; a malformed hash never authenticates."""
    try:
        return app.hasher.verify(app.settings.admin_password_hash.get_secret_value(), password)
    except (VerificationError, InvalidHashError):
        return False


def _client_of(request: Request, app: Container) -> str:
    """The client address used for counting failures (D-15)."""
    peer = request.client.host if request.client else UNKNOWN_PEER
    return resolve_client_address(peer, request.headers.get("x-forwarded-for"), app.trusted_proxies)


@open_router.post("/login")
def login(body: LoginRequest, request: Request) -> JSONResponse:
    """Check the password; on success set the session and CSRF cookies."""
    app = container(request)
    now = app.clock.now()
    client = _client_of(request, app)
    wait = app.guard.begin_attempt(client, now)
    if wait is not None:
        raise ApiError(429, RATE_LIMITED, headers={"Retry-After": str(wait)})
    if not _password_ok(app, body.password):
        throttled = app.guard.record_failure(client, now)
        app.audit.record(ACTOR_ANONYMOUS, "LOGIN_FAILED")
        if throttled:
            app.audit.record(ACTOR_SYSTEM, "SECURITY_LOGIN_THROTTLED")
        raise ApiError(401, INVALID_CREDENTIALS)
    app.guard.record_success(client)
    cookie, session = app.codec.issue(now)
    response = JSONResponse({"csrf_token": session.csrf_token})
    max_age = app.settings.session_ttl_minutes * 60
    secure = app.settings.cookie_secure
    response.set_cookie(
        SESSION_COOKIE, cookie, max_age=max_age, httponly=True, samesite="strict", secure=secure
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="strict",
        secure=secure,
    )
    app.audit.record(ACTOR_ADMIN, "LOGIN_SUCCEEDED")
    return response


@protected_router.post("/logout")
def logout(request: Request) -> JSONResponse:
    """Clear both cookies."""
    app = container(request)
    app.audit.record(ACTOR_ADMIN, "LOGOUT")
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, samesite="strict")
    return response
