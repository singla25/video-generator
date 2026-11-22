"""BL-8 SS-A*: the API gate while the database is behind the code.

CONTRACT (assumed names the developer must provide)
  AppDeps.schema_reader: a SchemaVersionReader (default: the real adapter).
  state behind/empty: every route except /health, /auth/* and /system/status answers
  503 {"code": "DB_NEEDS_MIGRATION", "message": <exact text>} without touching any table
  (the app here runs on an empty sqlite database, so any query would fail differently).
  /system/status gains "schema": {state, current, expected, message}.
  Startup logs one WARNING with the message when behind/empty.
Paths are as the app sees them (the /api prefix is added by the reverse proxy).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

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
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps

BEHIND_MESSAGE = "The database needs migration 0003 (it is at 0002). Ask the admin to run it."
EMPTY_MESSAGE = "The database needs migration 0003 (it is at none). Ask the admin to run it."
AHEAD_MESSAGE = "The database is newer than this version of the app."

Build = Callable[..., TestClient]


class Beat:
    """Heartbeat double: the worker is alive."""

    def beat(self) -> None:
        pass

    def is_alive(self) -> bool:
        return True


@pytest.fixture
def build(tmp_path: Path) -> Build:
    def factory(reader: FakeSchemaReader, *, login: bool = True) -> TestClient:
        assert "schema_reader" in {f.name for f in dataclasses.fields(AppDeps)}
        deps = AppDeps(
            clock=FakeClock(),
            speech_to_text=FakeSpeechToText(),
            video_probe=FakeVideoProbe(),
            storage=InMemoryStorage(),
            job_queue=FakeJobQueue(),
            worker_heartbeat=Beat(),
            schema_reader=reader,
        )
        settings = make_settings("sqlite://", tmp_path, redis_url=DSN)
        app = create_app(settings, deps=deps)
        box = app.state.container
        api = TestClient(app, raise_server_exceptions=False)
        if login:
            cookie, session = box.codec.issue(box.clock.now())
            api.cookies.set("vidgen_session", cookie)
            api.headers["X-CSRF-Token"] = session.csrf_token
        return api

    return factory


BLOCKED: list[tuple[str, str]] = [
    ("GET", "/batches"),
    ("GET", "/templates"),
    ("POST", "/templates"),  # template video upload
    ("POST", "/batches/inspect-sheet"),  # sheet upload
    ("GET", "/audit"),
    ("GET", "/stats/daily"),
]


@pytest.mark.parametrize("current", ["0002", "0001", None])
@pytest.mark.parametrize(("method", "path"), BLOCKED)
def test_behind_or_empty_blocks_data_routes_with_one_clear_message(
    build: Build, current: str | None, method: str, path: str
) -> None:
    """SS-A-P1: 503 DB_NEEDS_MIGRATION, exact text, in the standard {code, message} envelope."""
    response = build(FakeSchemaReader(current)).request(method, path)
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "DB_NEEDS_MIGRATION"
    expected = (
        EMPTY_MESSAGE
        if current is None
        else f"The database needs migration 0003 (it is at {current}). Ask the admin to run it."
    )
    assert body["message"] == expected


def test_blocked_body_has_no_stack_trace_or_sql(build: Build) -> None:
    """SS-A-N1: nothing but the fixed message reaches the client."""
    text = build(FakeSchemaReader("0002")).get("/batches").text
    for marker in ("Traceback", "SELECT", "sqlalchemy", "psycopg", 'File "', "sqlite"):
        assert marker not in text


def test_empty_still_allows_health_login_and_status(build: Build) -> None:
    """SS-A-P2: on an empty database (no tables) health, auth and status still answer.

    The behind case lives in tests/integration/api/test_schema_gate_behind.py: a behind database
    has its tables (DD-44), so it needs a real one, not this empty sqlite.
    """
    api = build(FakeSchemaReader(None))
    assert api.get("/health").json() == {"status": "ok"}
    assert api.get("/system/status").status_code == 200
    login = api.post("/auth/login", json={"password": "wrong password"})
    assert login.status_code != 503  # reaches the login handler (401 or throttled)
    assert api.post("/auth/logout").status_code != 503


def test_status_reports_the_schema_block(build: Build) -> None:
    """SS-A-P3: /system/status gains schema {state, current, expected, message}."""
    body = build(FakeSchemaReader("0002")).get("/system/status").json()
    assert body["schema"] == {
        "state": "behind",
        "current": "0002",
        "expected": "0003",
        "message": BEHIND_MESSAGE,
    }
    assert {"worker_alive", "queue_depth", "redis_ok", "ai_mode", "spoken_suffix"} <= set(
        body
    )  # unchanged keys


def test_status_for_empty_database_has_null_current(build: Build) -> None:
    """SS-A-P4."""
    schema = build(FakeSchemaReader(None)).get("/system/status").json()["schema"]
    assert (schema["state"], schema["current"], schema["message"]) == (
        "empty",
        None,
        EMPTY_MESSAGE,
    )


def test_status_for_ok_database(build: Build) -> None:
    """SS-A-P5."""
    schema = build(FakeSchemaReader("0003")).get("/system/status").json()["schema"]
    assert (schema["state"], schema["current"], schema["expected"]) == ("ok", "0003", "0003")


def test_ok_blocks_nothing(build: Build) -> None:
    """SS-A-P6: with the right schema no route answers DB_NEEDS_MIGRATION."""
    api = build(FakeSchemaReader("0003"))
    for method, path in BLOCKED:
        response = api.request(method, path)
        assert response.json().get("code") != "DB_NEEDS_MIGRATION", path


def test_ahead_blocks_nothing_and_says_so(build: Build) -> None:
    """SS-A-E1: a newer database does not block; the status carries the 'newer' sentence."""
    api = build(FakeSchemaReader("0004"))
    for method, path in BLOCKED:
        assert api.request(method, path).json().get("code") != "DB_NEEDS_MIGRATION", path
    schema = api.get("/system/status").json()["schema"]
    assert (schema["state"], schema["message"]) == ("ahead", AHEAD_MESSAGE)


def test_status_still_requires_a_session(build: Build) -> None:
    """SS-A-N2: the schema block is not public."""
    response = build(FakeSchemaReader("0002"), login=False).get("/system/status")
    assert response.status_code == 401
    assert "schema" not in response.json()


def test_health_is_unchanged_in_every_state(build: Build) -> None:
    """SS-A-P7."""
    for current in ("0002", None, "0003", "0004"):
        response = build(FakeSchemaReader(current), login=False).get("/health")
        assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_blocked_routes_do_not_read_the_schema_every_time(build: Build) -> None:
    """SS-A-E2: the TTL cache applies to requests (five calls, one read)."""
    reader = FakeSchemaReader("0002")
    api = build(reader)
    for _ in range(5):
        api.get("/batches")
    assert reader.current_calls == 1


def test_unreachable_database_keeps_the_existing_db_unavailable_answer(build: Build) -> None:
    """SS-A-N3: a reader that cannot connect gives the existing 503 DB_UNAVAILABLE, never 500.

    Health and the status screen still answer 200.
    """
    reader = FakeSchemaReader("0003")
    reader.fail_with = OperationalError("SELECT 1", {}, Exception("password=hunter2"))
    api = build(reader)
    response = api.get("/batches")
    assert (response.status_code, response.json()["code"]) == (503, "DB_UNAVAILABLE")
    assert "hunter2" not in response.text
    assert api.get("/health").status_code == 200
    assert api.get("/system/status").status_code == 200


def test_app_recovers_without_restart_after_migration(build: Build) -> None:
    """SS-A-E3: once the Admin migrates, blocked routes stop answering DB_NEEDS_MIGRATION.

    The app's fake clock is moved past the largest allowed TTL (300 s) so the cache expires.
    """
    reader = FakeSchemaReader("0002")
    api = build(reader)
    assert api.get("/batches").json()["code"] == "DB_NEEDS_MIGRATION"
    reader.current = "0003"
    api.app.state.container.clock.advance(seconds=301)  # type: ignore[attr-defined]
    assert api.get("/batches").json().get("code") != "DB_NEEDS_MIGRATION"


def test_startup_logs_one_warning_with_the_message(
    build: Build, caplog: pytest.LogCaptureFixture
) -> None:
    """SS-A-P8: one WARNING at startup, same text, no secrets."""
    with caplog.at_level(logging.WARNING), build(FakeSchemaReader("0002")):
        pass
    hits: list[Any] = [r for r in caplog.records if BEHIND_MESSAGE in r.getMessage()]
    assert len(hits) == 1
    assert hits[0].levelno == logging.WARNING
    assert "devpassword" not in caplog.text


def test_startup_logs_nothing_when_ok(build: Build, caplog: pytest.LogCaptureFixture) -> None:
    """SS-A-E4."""
    with caplog.at_level(logging.WARNING), build(FakeSchemaReader("0003")):
        pass
    assert not [r for r in caplog.records if "needs migration" in r.getMessage()]
