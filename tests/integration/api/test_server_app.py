"""The deployable server app mounts the API under /api (DD-21, defect D-F6-2).

Contract: ``vidgen.api.server.create_server_app(settings, deps=...)`` returns an ASGI app that
serves the existing API app (from ``create_app``) at ``/api``. Nothing of the API answers at the
root, so browser page loads of the SPA routes (/templates, /batches/...) never reach it. The
existing ``create_app`` stays as it is (its tests are unchanged).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.conftest import PASSWORD, Env, EnvFactory


@pytest.fixture
def server(make_env: EnvFactory) -> TestClient:
    """A client on the server app built from the same settings and doubles as ``make_env``."""
    # Imported here so a missing module fails these tests, not the whole collection.
    from vidgen.api.server import create_server_app

    env: Env = make_env(login=False)
    return TestClient(create_server_app(env.settings, deps=env.deps))


def login(client: TestClient) -> dict[str, str]:
    """Log in through /api and return the CSRF header."""
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_health_is_served_under_api(server: TestClient) -> None:
    """GET /api/health is open and answers ok."""
    response = server.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_routes_need_a_session_under_api(server: TestClient) -> None:
    """The mounted API still enforces authentication with the {code, message} body."""
    response = server.get("/api/batches")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "path", ["/batches", "/templates", "/audit", "/stats/daily", "/auth/login"]
)
def test_api_is_not_served_at_the_root(server: TestClient, path: str) -> None:
    """The old flat paths are gone: no API JSON at the root (so the SPA can own them)."""
    response = server.get(path)
    content_type = response.headers.get("content-type", "")
    assert response.status_code == 404 or "text/html" in content_type
    assert "UNAUTHENTICATED" not in response.text
    assert "application/json" not in content_type or response.status_code == 404


def test_login_and_a_protected_call_work_end_to_end_under_api(server: TestClient) -> None:
    """Cookies set by /api/auth/login are sent back to /api/... (cookie path covers /api)."""
    csrf = login(server)
    assert server.get("/api/batches").status_code == 200
    assert server.get("/api/templates").json() == {"templates": []}
    assert server.post("/api/auth/logout", headers=csrf).status_code == 200


def test_csrf_is_still_required_under_api(server: TestClient) -> None:
    """A state-changing call without the token is 403 CSRF_FAILED."""
    login(server)
    response = server.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"


def test_unknown_api_path_keeps_the_error_shape(server: TestClient) -> None:
    """A 404 below /api is the JSON error body, not an HTML page."""
    login(server)
    response = server.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_downloads_work_under_api(server: TestClient) -> None:
    """Video and ZIP URLs are built from the same prefix: an unknown batch is a JSON 404."""
    login(server)
    response = server.get("/api/batches/00000000-0000-4000-8000-000000000000/download.zip")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
