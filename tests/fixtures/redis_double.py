"""A tiny in-memory stand-in for the redis client (keys with a time to live).

Only what the worker heartbeat needs: ``set(name, value, ex=)``, ``exists(name)``, ``get``,
``ttl``. Time comes from the shared ``FakeClock``, so expiry is deterministic. ``down`` makes
every call raise the same error a stopped Redis gives.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from redis.exceptions import ConnectionError as RedisConnectionError

from tests.fixtures.doubles import FakeClock

DSN = "redis://:s3cret-redis-pw@redis-host:6379/0"


class FakeRedis:
    """Dict-backed redis with expiry."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._data: dict[str, tuple[bytes, datetime | None]] = {}
        self.down = False
        self.set_calls: list[tuple[str, bytes, int | None]] = []

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError(f"Error 111 connecting to {DSN}. Connection refused.")

    def _live(self, name: str) -> tuple[bytes, datetime | None] | None:
        item = self._data.get(name)
        if item is None:
            return None
        if item[1] is not None and self._clock.now() >= item[1]:
            del self._data[name]
            return None
        return item

    def set(self, name: str, value: str | bytes | int, ex: int | None = None) -> bool:
        """SET with an optional expiry in seconds."""
        self._check()
        raw = value if isinstance(value, bytes) else str(value).encode()
        expires = None if ex is None else self._clock.now() + timedelta(seconds=ex)
        self._data[name] = (raw, expires)
        self.set_calls.append((name, raw, ex))
        return True

    def get(self, name: str) -> bytes | None:
        """GET, or None when missing or expired."""
        self._check()
        item = self._live(name)
        return None if item is None else item[0]

    def exists(self, *names: str) -> int:
        """Number of the given keys that exist."""
        self._check()
        return sum(1 for n in names if self._live(n) is not None)

    def ttl(self, name: str) -> int:
        """Seconds left (-2 missing, -1 no expiry)."""
        self._check()
        item = self._live(name)
        if item is None:
            return -2
        if item[1] is None:
            return -1
        return int((item[1] - self._clock.now()).total_seconds())
