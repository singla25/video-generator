"""RedisStageReporter (T-PROG-BE): the preview stage lives in one expiring Redis key per batch.

CONTRACT
  RedisStageReporter(client, ttl_seconds=900) in vidgen.infrastructure.queue.redis_progress
  - report(batch_id, stage): key ``vidgen:stage:<batch_id>`` set with the TTL
  - current(batch_id): the stage, or None when the key is missing (or expired)
  - clear(batch_id): deletes the key
  Redis errors are not swallowed here; the render service and the API decide what to do.
Uses the no-network FakeRedis from tests/fixtures/redis_double.py (time from FakeClock).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from tests.fixtures.doubles import FakeClock
from tests.fixtures.redis_double import FakeRedis
from vidgen.infrastructure.queue.redis_progress import RedisStageReporter
from vidgen.ports.progress import StageReporter

DEFAULT_TTL = 900
BATCH = UUID("0b6c1f0e-3d2a-4c55-9a8e-7f1d2c3b4a59")


class _DeleteRedis(FakeRedis):
    """FakeRedis plus DEL, which the adapter needs for ``clear``."""

    def delete(self, *names: str) -> int:
        """Remove the given keys; returns how many existed."""
        self._check()
        removed = 0
        for name in names:
            if self._live(name) is not None:
                del self._data[name]
                removed += 1
        return removed


class _TextRedis(_DeleteRedis):
    """A client created with decode_responses=True: GET returns str."""

    def get(self, name: str) -> Any:
        """GET as text, or None when missing."""
        raw = super().get(name)
        return None if raw is None else raw.decode()


@pytest.fixture
def clock() -> FakeClock:
    """Shared fake time for the client's expiry."""
    return FakeClock()


@pytest.fixture
def client(clock: FakeClock) -> _DeleteRedis:
    """A fresh in-memory client."""
    return _DeleteRedis(clock)


def reporter(client: Any, ttl_seconds: int | None = None) -> RedisStageReporter:
    """The adapter on the given client, with the default TTL unless one is given."""
    if ttl_seconds is None:
        return RedisStageReporter(client)
    return RedisStageReporter(client, ttl_seconds=ttl_seconds)


# ---- positive ----------------------------------------------------------------------------


def test_report_then_current_returns_the_stage(client: _DeleteRedis) -> None:
    """P1: the stage reported for a batch is the one read back."""
    stages = reporter(client)
    stages.report(BATCH, "tts")
    assert stages.current(BATCH) == "tts"


def test_report_stores_the_key_in_the_stage_namespace(client: _DeleteRedis) -> None:
    """P2: the key is exactly vidgen:stage:<batch id>, with the id in its usual text form."""
    reporter(client).report(BATCH, "encode")
    assert client.get(f"vidgen:stage:{BATCH}") == b"encode"
    assert client.get(f"vidgen:stage:{BATCH.hex}") is None


def test_default_ttl_is_900_seconds(client: _DeleteRedis, clock: FakeClock) -> None:
    """P3: the stage is still there at 899 s and gone at 900 s."""
    reporter(client).report(BATCH, "fetch")
    clock.advance(seconds=DEFAULT_TTL - 1)
    assert reporter(client).current(BATCH) == "fetch"
    clock.advance(seconds=1)
    assert reporter(client).current(BATCH) is None


def test_custom_ttl_is_honoured(client: _DeleteRedis, clock: FakeClock) -> None:
    """P4: ttl_seconds replaces the default."""
    reporter(client, ttl_seconds=30).report(BATCH, "lipsync")
    clock.advance(seconds=29)
    assert reporter(client, ttl_seconds=30).current(BATCH) == "lipsync"
    clock.advance(seconds=1)
    assert reporter(client, ttl_seconds=30).current(BATCH) is None


def test_clear_removes_the_stage(client: _DeleteRedis) -> None:
    """P5: after clear the batch has no stage."""
    stages = reporter(client)
    stages.report(BATCH, "check")
    stages.clear(BATCH)
    assert stages.current(BATCH) is None
    assert client.get(f"vidgen:stage:{BATCH}") is None


def test_a_newer_report_replaces_the_stage_and_renews_the_ttl(
    client: _DeleteRedis, clock: FakeClock
) -> None:
    """P6: the latest stage wins, and reporting again restarts the TTL."""
    stages = reporter(client)
    stages.report(BATCH, "tts")
    clock.advance(seconds=800)
    stages.report(BATCH, "lipsync")
    clock.advance(seconds=800)  # 1600 s after the first report, 800 s after the second
    assert stages.current(BATCH) == "lipsync"


def test_two_batches_do_not_see_each_others_stage(client: _DeleteRedis) -> None:
    """P7: each batch has its own key."""
    other = uuid4()
    stages = reporter(client)
    stages.report(BATCH, "tts")
    stages.report(other, "encode")
    stages.clear(BATCH)
    assert stages.current(BATCH) is None
    assert stages.current(other) == "encode"


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize("operation", ["report", "current", "clear"])
def test_redis_outage_is_raised_to_the_caller(client: _DeleteRedis, operation: str) -> None:
    """N1: the adapter does not hide a Redis error; the caller decides (render logs it)."""
    stages = reporter(client)
    client.down = True
    with pytest.raises(RedisConnectionError):
        if operation == "report":
            stages.report(BATCH, "tts")
        elif operation == "current":
            stages.current(BATCH)
        else:
            stages.clear(BATCH)


@pytest.mark.parametrize("ttl", [0, -1, -900])
def test_non_positive_ttl_is_rejected(client: _DeleteRedis, ttl: int) -> None:
    """N2: a stage that never expires (or expires at once) is a configuration error."""
    with pytest.raises(ValueError, match="ttl"):
        RedisStageReporter(client, ttl_seconds=ttl)


# ---- edge --------------------------------------------------------------------------------


def test_current_on_a_missing_key_returns_none(client: _DeleteRedis) -> None:
    """E1: nothing reported yet means no stage."""
    assert reporter(client).current(BATCH) is None


def test_clear_on_a_missing_key_is_a_no_op(client: _DeleteRedis) -> None:
    """E2: clearing twice (or never reported) does not raise."""
    stages = reporter(client)
    stages.clear(BATCH)
    stages.clear(BATCH)
    assert stages.current(BATCH) is None


def test_text_replies_from_a_decode_responses_client_are_read(clock: FakeClock) -> None:
    """E3: a client that returns str instead of bytes still gives the stage name."""
    client = _TextRedis(clock)
    stages = reporter(client)
    stages.report(BATCH, "voice-check")
    assert stages.current(BATCH) == "voice-check"


def test_the_port_is_a_protocol_in_vidgen_ports() -> None:
    """E4: StageReporter is the port (a Protocol) the services depend on."""
    assert getattr(StageReporter, "_is_protocol", False) is True
