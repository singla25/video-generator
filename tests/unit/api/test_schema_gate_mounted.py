"""SS-M*: the schema gate on the DEPLOYABLE app, where the API is mounted under the API prefix.

Inside the mounted app the request path still carries the prefix, so the open-path check
must strip it. Before the fix, health and login were blocked on a behind/empty database.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.doubles import (
    FakeClock,
    FakeJobQueue,
    FakeSpeechToText,
    FakeVideoProbe,
    InMemoryStorage,
)
from tests.fixtures.redis_double import DSN
from tests.fixtures.schema_doubles import FakeSchemaReader
from tests.integration.api.conftest import make_settings
from tests.unit.api.test_schema_gate import BEHIND_MESSAGE, EMPTY_MESSAGE, Beat
from vidgen.api.app import create_app
from vidgen.api.container import AppDeps
from vidgen.api.server import API_PREFIX, create_server_app

Build = Callable[..., TestClient]
STATES = [("0002", BEHIND_MESSAGE), (None, EMPTY_MESSAGE)]


def _deps(reader: FakeSchemaReader) -> AppDeps:
    return AppDeps(
        clock=FakeClock(),
        speech_to_text=FakeSpeechToText(),
        video_probe=FakeVideoProbe(),
        storage=InMemoryStorage(),
        job_queue=FakeJobQueue(),
        worker_heartbeat=Beat(),
        schema_reader=reader,
    )


def _p(path: str) -> str:
    """Prefix a route path with the deployable app's API mount."""
    return f"{API_PREFIX}{path}"


@pytest.fixture
def build(tmp_path: Path) -> Build:
    def factory(reader: FakeSchemaReader, *, mounted: bool = True) -> TestClient:
        settings = make_settings("sqlite://", tmp_path, redis_url=DSN)
        if mounted:
            server = create_server_app(settings, deps=_deps(reader))
            inner = next(r.app for r in server.routes if getattr(r, "path", "") == API_PREFIX)  # type: ignore[attr-defined]
        else:
            inner = server = create_app(settings, deps=_deps(reader))
        box = inner.state.container
        api = TestClient(server, raise_server_exceptions=False)
        cookie, session = box.codec.issue(box.clock.now())
        api.cookies.set("vidgen_session", cookie)
        api.headers["X-CSRF-Token"] = session.csrf_token
        return api

    return factory


def _is_gated(response: object) -> bool:
    body = (
        response.json()
        if getattr(response, "headers", {}).get("content-type", "").startswith("application/json")
        else {}
    )
    return getattr(response, "status_code", 0) == 503 and body.get("code") == "DB_NEEDS_MIGRATION"


@pytest.mark.parametrize(("current", "_message"), STATES)
def test_mounted_health_answers_200_when_behind_or_empty(
    build: Build, current: str | None, _message: str
) -> None:
    """SS-M-P1: health under the mount is open."""
    response = build(FakeSchemaReader(current)).get(_p("/health"))
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


@pytest.mark.parametrize(("current", "_message"), STATES)
@pytest.mark.parametrize("path", ["/auth/login", "/auth/logout"])
def test_mounted_auth_routes_are_not_blocked_by_the_gate(
    build: Build, current: str | None, _message: str, path: str
) -> None:
    """SS-M-P2: login and logout reach their handlers (401/422/200 are all fine)."""
    response = build(FakeSchemaReader(current)).post(_p(path), json={"password": "x"})
    assert not _is_gated(response), (path, response.text)


@pytest.mark.parametrize(("current", "_message"), STATES)
def test_mounted_system_status_is_not_blocked_and_reports_schema(
    build: Build, current: str | None, _message: str
) -> None:
    """SS-M-P3: the authenticated status route still answers and carries the schema block."""
    response = build(FakeSchemaReader(current)).get(_p("/system/status"))
    assert response.status_code == 200
    assert "schema" in response.json()


@pytest.mark.parametrize(("current", "message"), STATES)
@pytest.mark.parametrize("path", ["/batches", "/templates"])
def test_mounted_data_routes_answer_503_with_the_exact_message(
    build: Build, current: str | None, message: str, path: str
) -> None:
    """SS-M-P4."""
    response = build(FakeSchemaReader(current)).get(_p(path))
    assert response.status_code == 503
    assert response.json() == {"code": "DB_NEEDS_MIGRATION", "message": message}


@pytest.mark.parametrize("path", ["/batches", "/templates", "/health"])
def test_mounted_ok_state_blocks_nothing(build: Build, path: str) -> None:
    """SS-M-P5."""
    assert not _is_gated(build(FakeSchemaReader("0003")).get(_p(path)))


@pytest.mark.parametrize(
    "path",
    [
        "/batches/health",
        "/templates/health",
        "/batches/auth/x",
        "/health/extra",
        "/authx/login",
        "/system/status/extra",
    ],
)
def test_mounted_paths_that_only_contain_an_open_word_stay_blocked(build: Build, path: str) -> None:
    """SS-M-E1: no substring match; only the exact open paths are open."""
    assert _is_gated(build(FakeSchemaReader("0002")).get(_p(path))), path


@pytest.mark.parametrize(("current", "message"), STATES)
def test_unmounted_app_behaves_as_before(build: Build, current: str | None, message: str) -> None:
    """SS-M-E3: without a prefix mount health is open and data routes are blocked."""
    api = build(FakeSchemaReader(current), mounted=False)
    assert api.get("/health").status_code == 200
    assert not _is_gated(api.post("/auth/login", json={"password": "x"}))
    blocked = api.get("/batches")
    assert blocked.status_code == 503
    assert blocked.json()["message"] == message
