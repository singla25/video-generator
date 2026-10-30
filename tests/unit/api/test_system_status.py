"""FIX-WORKER-1 (DD-29): GET /system/status tells the dashboard whether the worker is running.

CONTRACT
  GET /system/status (session required, no CSRF needed for GET) -> 200
      {"worker_alive": bool, "queue_depth": int | null, "redis_ok": bool,
      "ai_mode": "fake" | "local"}   (L1b: ai_mode is Settings.ai_mode; never needs Redis or the DB)
  AppDeps gains ``worker_heartbeat`` (a WorkerHeartbeat); queue depth is ``job_queue.depth()``
  when the queue has it. Redis down: still 200 with worker_alive=false, redis_ok=false,
  queue_depth=null (NOT the 503 QUEUE_UNAVAILABLE envelope). The route never touches the
  database and never echoes connection strings.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from tests.fixtures.doubles import (
    FakeClock,
    FakeJobQueue,
    FakeSpeechToText,
    FakeVideoProbe,
    InMemoryStorage,
)
from tests.fixtures.redis_double import DSN, FakeRedis
from tests.integration.api.conftest import make_settings
from vidgen.api.app import create_app
from vidgen.api.deps import AppDeps
from vidgen.infrastructure.db.uow import SqlUnitOfWork

SECRET = "s3cret-redis-pw"  # noqa: S105 - marker that must never leak
KEYS = {"worker_alive", "queue_depth", "redis_ok", "ai_mode"}


class DepthQueue(FakeJobQueue):
    """A queue that can report how many jobs wait."""

    def __init__(self, depth: int | Exception = 0) -> None:
        super().__init__()
        self._depth = depth

    def depth(self) -> int:
        if isinstance(self._depth, Exception):
            raise self._depth
        return self._depth


class Beat:
    """A heartbeat double with a settable answer (the adapter has its own tests)."""

    def __init__(self, alive: bool | Exception) -> None:
        self.alive = alive

    def beat(self) -> None:
        self.alive = True

    def is_alive(self) -> bool:
        if isinstance(self.alive, Exception):
            raise self.alive
        return self.alive


Build = Callable[..., TestClient]


@pytest.fixture
def build(tmp_path: Path) -> Iterator[Build]:
    def factory(
        heartbeat: Any,
        queue: FakeJobQueue | None = None,
        *,
        login: bool = True,
        **settings_overrides: Any,
    ) -> TestClient:
        fields = {f.name for f in dataclasses.fields(AppDeps)}
        args: dict[str, Any] = {
            "clock": FakeClock(),
            "speech_to_text": FakeSpeechToText(),
            "video_probe": FakeVideoProbe(),
            "storage": InMemoryStorage(),
            "job_queue": queue or DepthQueue(),
        }
        if "worker_heartbeat" in fields:  # missing today: the route test then fails on 404
            args["worker_heartbeat"] = heartbeat
        settings = make_settings("sqlite://", tmp_path, redis_url=DSN, **settings_overrides)
        app = create_app(settings, deps=AppDeps(**args))
        box = app.state.container
        api = TestClient(app, raise_server_exceptions=False)
        if login:
            cookie, session = box.codec.issue(box.clock.now())
            api.cookies.set("vidgen_session", cookie)
            api.headers["X-CSRF-Token"] = session.csrf_token
        return api

    yield factory


def test_requires_a_session(build: Build) -> None:
    response = build(Beat(True), login=False).get("/system/status")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_reports_a_live_worker_and_the_queue_depth(build: Build) -> None:
    response = build(Beat(True), DepthQueue(7)).get("/system/status")
    assert response.status_code == 200
    assert response.json() == {
        "worker_alive": True,
        "queue_depth": 7,
        "redis_ok": True,
        "ai_mode": "fake",
    }


def test_reports_a_stopped_worker(build: Build) -> None:
    body = build(Beat(False), DepthQueue(3)).get("/system/status").json()
    assert body == {"worker_alive": False, "queue_depth": 3, "redis_ok": True, "ai_mode": "fake"}


def test_the_answer_follows_the_heartbeat_over_time(build: Build) -> None:
    beat = Beat(True)
    api = build(beat)
    assert api.get("/system/status").json()["worker_alive"] is True
    beat.alive = False  # the heartbeat key expired
    assert api.get("/system/status").json()["worker_alive"] is False
    beat.beat()
    assert api.get("/system/status").json()["worker_alive"] is True


def test_works_with_the_real_adapter_and_expiry(build: Build) -> None:
    from vidgen.infrastructure.queue.redis_heartbeat import RedisWorkerHeartbeat

    clock = FakeClock()
    redis = FakeRedis(clock)
    heartbeat = RedisWorkerHeartbeat(redis)
    api = build(heartbeat)
    assert api.get("/system/status").json()["worker_alive"] is False
    heartbeat.beat()
    assert api.get("/system/status").json()["worker_alive"] is True
    clock.advance(seconds=15)
    assert api.get("/system/status").json()["worker_alive"] is False


def test_redis_down_answers_200_with_redis_ok_false(build: Build) -> None:
    down = RedisConnectionError(f"Error 111 connecting to {DSN}. Connection refused.")
    response = build(Beat(down), DepthQueue(down)).get("/system/status")
    assert response.status_code == 200
    assert response.json() == {
        "worker_alive": False,
        "queue_depth": None,
        "redis_ok": False,
        "ai_mode": "fake",
    }
    for marker in (SECRET, "redis-host", "redis://", "Traceback"):
        assert marker not in response.text


def test_queue_depth_failure_alone_gives_null_depth(build: Build) -> None:
    body = build(Beat(True), DepthQueue(RedisConnectionError("x"))).get("/system/status").json()
    assert body["queue_depth"] is None
    assert body["worker_alive"] is True


def test_depth_is_the_number_the_queue_reports(build: Build) -> None:
    queue = FakeJobQueue()
    queue.enqueue_preview(uuid4(), uuid4())
    queue.enqueue_rows(uuid4(), [uuid4(), uuid4()])
    body = build(Beat(True), queue).get("/system/status").json()
    assert body["queue_depth"] == 3


def test_depth_raising_a_redis_error_gives_null_and_200(build: Build) -> None:
    response = build(Beat(True), DepthQueue(RedisConnectionError("down"))).get("/system/status")
    assert response.status_code == 200
    assert response.json()["queue_depth"] is None


def test_exactly_the_documented_keys_and_no_secrets(build: Build) -> None:
    response = build(Beat(True)).get("/system/status")
    assert set(response.json()) == KEYS
    for marker in (SECRET, "redis://", DSN):
        assert marker not in response.text


def test_does_not_need_the_database(build: Build, monkeypatch: pytest.MonkeyPatch) -> None:
    """The banner must still work when Postgres is the thing that is down."""

    def refuse(self: SqlUnitOfWork) -> SqlUnitOfWork:
        raise RuntimeError("database used")

    monkeypatch.setattr(SqlUnitOfWork, "__enter__", refuse)
    assert build(Beat(True)).get("/system/status").status_code == 200


def test_post_is_not_allowed(build: Build) -> None:
    response = build(Beat(True)).post("/system/status")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.parametrize("mode", ["fake", "local"])
def test_reports_the_configured_ai_mode(build: Build, mode: str) -> None:
    body = build(Beat(True), ai_mode=mode).get("/system/status").json()
    assert body["ai_mode"] == mode


def test_ai_mode_is_reported_even_when_redis_is_down(build: Build) -> None:
    down = RedisConnectionError("down")
    body = build(Beat(down), DepthQueue(down), ai_mode="local").get("/system/status").json()
    assert body["redis_ok"] is False
    assert body["ai_mode"] == "local"
