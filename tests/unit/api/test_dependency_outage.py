"""FIX-UPLOAD-1 (AC4): an unreachable database or queue is a clean 503, never a bare 500.

No real database or Redis is involved: the unit of work is made to raise the same SQLAlchemy
errors a stopped Postgres produces, and the queue errors come from the redis client itself.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import InterfaceError, OperationalError

from tests.fixtures.doubles import (
    VALID_VIDEO,
    FakeClock,
    FakeJobQueue,
    FakeSpeechToText,
    FakeVideoProbe,
    InMemoryStorage,
)
from tests.integration.api.conftest import make_settings
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps
from vidgen.infrastructure.db.uow import SqlUnitOfWork

SECRET = "hunter2-db-password"  # noqa: S105 - marker that must never leak
DSN = f"postgresql://vidgen:{SECRET}@db-host:5432/vidgen"
REFUSED = f'connection to server at "db-host", port 5432 failed: Connection refused (dsn {DSN})'
FORBIDDEN = (SECRET, "db-host", "postgresql://", "Traceback", "sqlalchemy", "psycopg", "redis://")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A logged-in client (cookie minted directly: login itself needs the database)."""
    settings = make_settings("sqlite://", tmp_path)
    deps = AppDeps(
        clock=FakeClock(),
        speech_to_text=FakeSpeechToText(),
        video_probe=FakeVideoProbe(),
        storage=InMemoryStorage(),
        job_queue=FakeJobQueue(),
    )
    app = create_app(settings, deps=deps)
    box = app.state.container
    cookie, session = box.codec.issue(box.clock.now())
    api = TestClient(app, raise_server_exceptions=False)
    api.cookies.set("vidgen_session", cookie)
    api.headers["X-CSRF-Token"] = session.csrf_token
    yield api


def _db_down(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def refuse(self: SqlUnitOfWork) -> SqlUnitOfWork:
        raise error

    monkeypatch.setattr(SqlUnitOfWork, "__enter__", refuse)


def _operational() -> Exception:
    return OperationalError("SELECT 1", {}, Exception(REFUSED))


def _interface() -> Exception:
    return InterfaceError("SELECT 1", {}, Exception(REFUSED))


def _assert_unavailable(response: Any, code: str) -> None:
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert body["message"].strip()
    for marker in FORBIDDEN:
        assert marker not in response.text


@pytest.mark.parametrize("make_error", [_operational, _interface])
def test_database_down_on_read_returns_503_db_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_error: Callable[[], Exception]
) -> None:
    """AC4 positive: GET /templates while Postgres refuses connections."""
    _db_down(monkeypatch, make_error())
    _assert_unavailable(client.get("/templates"), "DB_UNAVAILABLE")


def test_database_down_on_template_upload_returns_503_db_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: the very request the Admin saw fail (an upload) gets a 503 with the envelope."""
    _db_down(monkeypatch, _operational())
    response = client.post(
        "/templates",
        files={"video": ("t.mp4", VALID_VIDEO, "video/mp4")},
        data={"original_name": "Krishan"},
    )
    _assert_unavailable(response, "DB_UNAVAILABLE")


def test_database_down_on_batch_list_returns_503_db_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: any endpoint, not only templates."""
    _db_down(monkeypatch, _operational())
    _assert_unavailable(client.get("/batches"), "DB_UNAVAILABLE")


def test_database_down_message_is_plain_words(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: the message tells the operator what to do, in words, not jargon."""
    _db_down(monkeypatch, _operational())
    message = client.get("/templates").json().get("message", "")
    assert "try again" in message.lower()


def test_database_down_is_logged_at_error_level_without_the_connection_string(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC4: operators see the outage in the logs, but the DSN/password stays out of them."""
    _db_down(monkeypatch, _operational())
    with caplog.at_level(logging.DEBUG):
        client.get("/templates")
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], "log it at error level"
    assert SECRET not in caplog.text


def test_other_server_errors_stay_internal_error_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard against over-mapping: a plain bug is still INTERNAL_ERROR 500."""

    def boom(self: SqlUnitOfWork) -> SqlUnitOfWork:
        raise RuntimeError("bug")

    monkeypatch.setattr(SqlUnitOfWork, "__enter__", boom)
    response = client.get("/templates")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


def _redis_down() -> Exception:
    return RedisConnectionError(f"Error 111 connecting to redis://:{SECRET}@db-host:6379")


def _refused() -> Exception:
    return ConnectionRefusedError(111, "Connection refused")


def _route_that_enqueues(client: TestClient, error: Exception) -> None:
    class DownQueue(FakeJobQueue):
        def enqueue_preview(self, batch_id: uuid.UUID, row_id: uuid.UUID) -> None:
            raise error

    def enqueue(request: Request) -> dict[str, str]:
        DownQueue().enqueue_preview(uuid.uuid4(), uuid.uuid4())
        return {}

    client.app.add_api_route("/_probe/enqueue", enqueue, methods=["POST"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("make_error", [_redis_down, _refused])
def test_queue_unreachable_on_enqueue_returns_503_queue_unavailable(
    client: TestClient, make_error: Callable[[], Exception]
) -> None:
    """AC4: Redis/broker down when a job is handed over."""
    _route_that_enqueues(client, make_error())
    _assert_unavailable(client.post("/_probe/enqueue"), "QUEUE_UNAVAILABLE")


def test_queue_unreachable_is_logged_at_error_level(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """AC4: logged at error level, without the broker URL."""
    _route_that_enqueues(client, _redis_down())
    with caplog.at_level(logging.DEBUG):
        client.post("/_probe/enqueue")
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert SECRET not in caplog.text
