"""Signed session cookie and CSRF token handling (ADR-006)."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from itsdangerous import BadSignature, URLSafeSerializer

SESSION_COOKIE = "vidgen_session"
CSRF_COOKIE = "vidgen_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SALT = "vidgen-session"
CSRF_BYTES = 32


@dataclass(frozen=True)
class Session:
    """Data carried by a valid session cookie."""

    csrf_token: str
    issued_at: datetime


def csrf_matches(expected: str, supplied: str | None) -> bool:
    """Constant-time comparison of the session's CSRF token with the request header."""
    if not supplied:
        return False
    return hmac.compare_digest(expected.encode(), supplied.encode())


class SessionCodec:
    """Creates and reads signed, expiring, versioned session cookies."""

    def __init__(self, secret: str, version: int, ttl: timedelta) -> None:
        self._serializer = URLSafeSerializer(secret, salt=_SALT)
        self._version = version
        self._ttl = ttl

    def issue(self, now: datetime) -> tuple[str, Session]:
        """Return (cookie value, session) for a new login."""
        session = Session(secrets.token_urlsafe(CSRF_BYTES), now)
        payload = {"v": self._version, "iat": now.timestamp(), "csrf": session.csrf_token}
        return str(self._serializer.dumps(payload)), session

    def read(self, cookie: str | None, now: datetime) -> Session | None:
        """Return the session if the cookie is genuine, current-version and not expired."""
        if not cookie:
            return None
        try:
            payload = self._serializer.loads(cookie)
            issued = datetime.fromtimestamp(float(payload["iat"]), now.tzinfo)
            valid = payload["v"] == self._version and now - issued <= self._ttl
            return Session(str(payload["csrf"]), issued) if valid else None
        except (BadSignature, KeyError, TypeError, ValueError):
            return None
