"""Queue depth must work with the real Dramatiq RedisBroker (its ``queues`` is a set)."""

from __future__ import annotations

from typing import Any

from dramatiq.brokers.redis import RedisBroker

from vidgen.infrastructure.queue.dramatiq_queue import DEFAULT_QUEUE, DramatiqJobQueue


class _FakeRedis:
    """Minimal redis client: only what RedisBroker construction and depth need. No network."""

    def __init__(self, lengths: dict[str, int]) -> None:
        self._lengths = lengths

    def register_script(self, _script: str) -> Any:
        return lambda *a, **k: None

    def llen(self, key: str) -> int:
        return self._lengths.get(key, 0)


def _queue(n: int) -> DramatiqJobQueue:
    client = _FakeRedis({f"dramatiq:{DEFAULT_QUEUE}": n})
    broker = RedisBroker(client=client)  # type: ignore[arg-type]
    return DramatiqJobQueue(broker)


def test_depth_with_real_redis_broker_returns_waiting_count() -> None:
    assert _queue(3).depth() == 3


def test_depth_with_real_redis_broker_empty_queue_is_zero() -> None:
    assert _queue(0).depth() == 0
