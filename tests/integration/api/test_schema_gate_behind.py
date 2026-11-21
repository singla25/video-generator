"""BL-8 SS-A-P2 / SS-A-N4 (DD-44): a database that is behind the code still HAS its tables.

Only newer columns are missing, so the normal login guard and audit writes run unchanged:
brute-force protection is not weakened. Runs on the real test database with all tables.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

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


class Beat:
    """Heartbeat double: the worker is alive."""

    def beat(self) -> None:
        pass

    def is_alive(self) -> bool:
        return True


@pytest.fixture
def behind_api(db: Engine, test_db_url: str, tmp_path: Path) -> TestClient:
    """An app whose schema reader says the database is at 0002, on a database with tables."""
    deps = AppDeps(
        clock=FakeClock(),
        speech_to_text=FakeSpeechToText(),
        video_probe=FakeVideoProbe(),
        storage=InMemoryStorage(),
        job_queue=FakeJobQueue(),
        worker_heartbeat=Beat(),
        schema_reader=FakeSchemaReader("0002"),
    )
    app = create_app(make_settings(test_db_url, tmp_path, redis_url=DSN), deps=deps)
    return TestClient(app, raise_server_exceptions=False)


def test_behind_with_tables_allows_health_login_and_status_but_blocks_data(
    behind_api: TestClient,
) -> None:
    """SS-A-P2: health, login and status work; other routes answer 503 DB_NEEDS_MIGRATION."""
    assert behind_api.get("/health").json() == {"status": "ok"}
    login = behind_api.post("/auth/login", json={"password": "wrong password"})
    assert login.status_code == 401  # the real handler ran against the real tables
    assert behind_api.post("/auth/logout").status_code != 503
    box = behind_api.app.state.container  # type: ignore[attr-defined]
    cookie, session = box.codec.issue(box.clock.now())
    behind_api.cookies.set("vidgen_session", cookie)
    assert behind_api.get("/system/status").status_code == 200
    assert behind_api.get("/batches").json()["code"] == "DB_NEEDS_MIGRATION"
    assert session.csrf_token


def test_behind_login_throttle_still_counts_failures_and_locks_out(behind_api: TestClient) -> None:
    """SS-A-N4: five failures are 401, the sixth is 429 RATE_LIMITED: the guard is not weakened."""
    for _ in range(5):
        assert behind_api.post("/auth/login", json={"password": "bad"}).status_code == 401
    locked = behind_api.post("/auth/login", json={"password": "bad"})
    assert locked.status_code == 429
    assert locked.json()["code"] == "RATE_LIMITED"
