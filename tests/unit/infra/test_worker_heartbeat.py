"""FIX-WORKER-1 (DD-29): the worker heartbeat port and its Redis adapter.

CONTRACT
  vidgen.ports.WorkerHeartbeat (Protocol):  beat() -> None ;  is_alive() -> bool
  vidgen.infrastructure.queue.redis_heartbeat:
      DEFAULT_KEY == "vidgen:worker:heartbeat", DEFAULT_TTL_SECONDS == 15,
      HEARTBEAT_INTERVAL_SECONDS == 5
      RedisWorkerHeartbeat(client, *, key=DEFAULT_KEY, ttl_seconds=DEFAULT_TTL_SECONDS)
        beat()      SET key value EX ttl; a redis error is logged at error level and NOT raised
                    (a worker must not die because Redis blinked)
        is_alive()  True while the key exists; a redis error propagates (the route turns it
                    into redis_ok=false)
"""

from __future__ import annotations

import logging

import pytest
from redis.exceptions import RedisError

from tests.fixtures.doubles import FakeClock
from tests.fixtures.redis_double import DSN, FakeRedis
from vidgen.infrastructure.queue.redis_heartbeat import (
    DEFAULT_KEY,
    DEFAULT_TTL_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    RedisWorkerHeartbeat,
)
from vidgen.ports import WorkerHeartbeat


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def redis(clock: FakeClock) -> FakeRedis:
    return FakeRedis(clock)


def test_constants_match_the_design() -> None:
    """DD-29: key, 15 s life, refreshed every 5 s (at least 2 beats fit in one life)."""
    assert DEFAULT_KEY == "vidgen:worker:heartbeat"
    assert DEFAULT_TTL_SECONDS == 15
    assert HEARTBEAT_INTERVAL_SECONDS == 5
    assert HEARTBEAT_INTERVAL_SECONDS * 2 <= DEFAULT_TTL_SECONDS


def test_adapter_satisfies_the_port(redis: FakeRedis) -> None:
    beat: WorkerHeartbeat = RedisWorkerHeartbeat(redis)
    assert callable(beat.beat) and callable(beat.is_alive)


def test_no_beat_yet_means_not_alive(redis: FakeRedis) -> None:
    assert RedisWorkerHeartbeat(redis).is_alive() is False


def test_beat_sets_the_key_with_the_ttl(redis: FakeRedis) -> None:
    RedisWorkerHeartbeat(redis).beat()
    assert [(name, ex) for name, _, ex in redis.set_calls] == [(DEFAULT_KEY, 15)]


def test_alive_right_after_a_beat(redis: FakeRedis) -> None:
    heartbeat = RedisWorkerHeartbeat(redis)
    heartbeat.beat()
    assert heartbeat.is_alive() is True


def test_alive_just_before_the_ttl_and_dead_at_the_ttl(redis: FakeRedis, clock: FakeClock) -> None:
    """Boundary: 14.9 s is alive, 15 s is gone (a stopped worker is seen within ~15 s)."""
    heartbeat = RedisWorkerHeartbeat(redis)
    heartbeat.beat()
    clock.advance(seconds=14.9)
    assert heartbeat.is_alive() is True
    clock.advance(seconds=0.1)
    assert heartbeat.is_alive() is False


def test_a_new_beat_extends_the_life(redis: FakeRedis, clock: FakeClock) -> None:
    heartbeat = RedisWorkerHeartbeat(redis)
    heartbeat.beat()
    clock.advance(seconds=10)
    heartbeat.beat()
    clock.advance(seconds=10)  # 20 s since the first beat, 10 s since the second
    assert heartbeat.is_alive() is True


def test_a_beat_after_expiry_revives_it(redis: FakeRedis, clock: FakeClock) -> None:
    heartbeat = RedisWorkerHeartbeat(redis)
    heartbeat.beat()
    clock.advance(seconds=60)
    assert heartbeat.is_alive() is False
    heartbeat.beat()
    assert heartbeat.is_alive() is True


def test_two_workers_share_the_signal_and_one_stopping_does_not_hide_the_other(
    redis: FakeRedis, clock: FakeClock
) -> None:
    first, second = RedisWorkerHeartbeat(redis), RedisWorkerHeartbeat(redis)
    first.beat()
    second.beat()
    for _ in range(4):  # only the second keeps running
        clock.advance(seconds=5)
        second.beat()
    assert first.is_alive() is True  # the system as a whole has a live worker
    assert second.is_alive() is True


def test_all_workers_stopped_is_detected(redis: FakeRedis, clock: FakeClock) -> None:
    first, second = RedisWorkerHeartbeat(redis), RedisWorkerHeartbeat(redis)
    first.beat()
    second.beat()
    clock.advance(seconds=15)
    assert first.is_alive() is False


def test_custom_key_and_ttl(redis: FakeRedis, clock: FakeClock) -> None:
    heartbeat = RedisWorkerHeartbeat(redis, key="other:key", ttl_seconds=4)
    heartbeat.beat()
    assert redis.exists("other:key") == 1
    clock.advance(seconds=4)
    assert heartbeat.is_alive() is False


def test_redis_down_makes_is_alive_raise_a_redis_error(redis: FakeRedis) -> None:
    redis.down = True
    with pytest.raises(RedisError):
        RedisWorkerHeartbeat(redis).is_alive()


def test_redis_down_on_beat_is_logged_and_not_raised(
    redis: FakeRedis, caplog: pytest.LogCaptureFixture
) -> None:
    redis.down = True
    with caplog.at_level(logging.DEBUG):
        RedisWorkerHeartbeat(redis).beat()  # must not raise
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "s3cret-redis-pw" not in caplog.text
    assert DSN not in caplog.text


def test_the_stored_value_holds_no_secret_or_personal_data(redis: FakeRedis) -> None:
    RedisWorkerHeartbeat(redis).beat()
    value = redis.get(DEFAULT_KEY)
    assert value is not None and len(value) < 100
    assert b"redis://" not in value


def test_heartbeat_loop_beats_at_start_repeatedly_and_stops() -> None:
    """HeartbeatLoop: one beat at once, more on the interval, none after stop()."""
    import threading
    import time

    from vidgen.infrastructure.queue.redis_heartbeat import HeartbeatLoop

    beats: list[int] = []
    enough = threading.Event()

    class Counter:
        def beat(self) -> None:
            beats.append(1)
            if len(beats) >= 3:
                enough.set()

    loop = HeartbeatLoop(Counter(), 0.01)
    loop.start()
    assert len(beats) >= 1
    assert enough.wait(timeout=2)
    loop.stop()
    settled = len(beats)
    time.sleep(0.05)
    assert len(beats) == settled
    loop.stop()  # a second stop is harmless
