"""Cookie helpers for the API test client.

Why this exists: under httpx2 (the TestClient transport when it is installed) ``cookies.set``
adds a second jar entry next to the cookie the server already set. The request then carries
both values, and the server reads the genuine one. Deleting the name first makes the given value
the only cookie sent, with the same result under httpx.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def send_only_cookie(client: TestClient, name: str, value: str) -> None:
    """Make ``value`` the only cookie called ``name`` that ``client`` sends."""
    client.cookies.delete(name)
    client.cookies.set(name, value)
