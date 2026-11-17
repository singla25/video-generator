"""RP-HB: the worker heartbeat is per queue (AC2). Uses the redis double with the fake clock.

EXPECTED API (vidgen.infrastructure.queue.redis_heartbeat)
  queue_heartbeat_key(queue: str) -> str          "vidgen:worker:heartbeat:<queue>"
  RedisQueueHeartbeats(client, *, ttl_seconds=15)
      .beat(queue): renews that queue's key; a Redis error is logged (type only) and not raised
      .is_alive(queue) -> bool: True while the key exists; Redis errors propagate
"""

from __future__ import annotations

import logging

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from tests.fixtures.doubles import FakeClock
from tests.fixtures.redis_double import DSN, FakeRedis
from vidgen.infrastructure.queue.redis_heartbeat import RedisQueueHeartbeats, queue_heartbeat_key


def make() -> tuple[RedisQueueHeartbeats, FakeRedis, FakeClock]:
    clock = FakeClock()
    redis = FakeRedis(clock)
    return RedisQueueHeartbeats(redis, ttl_seconds=15), redis, clock


def test_a_beat_makes_only_its_own_queue_alive() -> None:
    """RP-HB-P1."""
    beats, _redis, _clock = make()
    beats.beat("vidgen.local-mac")
    assert beats.is_alive("vidgen.local-mac")
    assert not beats.is_alive("vidgen.modal-demo")


def test_keys_are_distinct_per_queue_and_carry_the_ttl() -> None:
    """RP-HB-P2."""
    beats, redis, _clock = make()
    beats.beat("a")
    beats.beat("b")
    assert queue_heartbeat_key("a") != queue_heartbeat_key("b")
    assert queue_heartbeat_key("a").endswith(":a")
    assert redis.ttl(queue_heartbeat_key("a")) == 15


def test_the_heartbeat_expires_when_the_worker_stops_beating() -> None:
    """RP-HB-E1: expiry during a batch turns the provider to 'needs setup'."""
    beats, _redis, clock = make()
    beats.beat("a")
    clock.advance(seconds=16)
    assert not beats.is_alive("a")


def test_two_workers_on_one_queue_keep_it_alive_until_both_stop() -> None:
    """RP-HB-E2: they share the key; any beat renews it."""
    beats, _redis, clock = make()
    beats.beat("a")  # worker 1
    clock.advance(seconds=10)
    beats.beat("a")  # worker 2
    clock.advance(seconds=10)  # worker 1 is gone, worker 2 renewed 10 s ago
    assert beats.is_alive("a")
    clock.advance(seconds=10)
    assert not beats.is_alive("a")


def test_a_redis_outage_is_logged_without_the_dsn_and_not_raised_on_beat(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RP-HB-N1."""
    beats, redis, _clock = make()
    redis.down = True
    with caplog.at_level(logging.ERROR):
        beats.beat("a")
    assert DSN not in caplog.text
    assert "s3cret" not in caplog.text


def test_is_alive_propagates_a_redis_outage() -> None:
    """RP-HB-N2: the API must be able to report 'redis down' instead of 'worker down'."""
    beats, redis, _clock = make()
    redis.down = True
    with pytest.raises(RedisConnectionError):
        beats.is_alive("a")
