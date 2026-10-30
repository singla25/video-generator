"""Worker heartbeat on Redis: a key with a short life that running workers keep renewing.

If every worker stops, the key expires and the API reports the worker as not alive.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

DEFAULT_KEY = "vidgen:worker:heartbeat"
DEFAULT_TTL_SECONDS = 15
HEARTBEAT_INTERVAL_SECONDS = 5
_MARKER = "1"  # the value carries no data; only the key's existence matters


class RedisWorkerHeartbeat:
    """``WorkerHeartbeat`` backed by one expiring Redis key shared by all workers."""

    def __init__(
        self, client: Any, *, key: str = DEFAULT_KEY, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> None:
        self._client = client
        self._key = key
        self._ttl = ttl_seconds

    def beat(self) -> None:
        """Renew the key. A Redis error is logged (type only, no DSN) and not raised."""
        try:
            self._client.set(self._key, _MARKER, ex=self._ttl)
        except RedisError as exc:
            logger.error("worker heartbeat failed", extra={"error_type": type(exc).__name__})

    def is_alive(self) -> bool:
        """True while the key exists. Redis errors propagate to the caller."""
        return bool(self._client.exists(self._key))


class HeartbeatLoop:
    """Calls ``beat`` every ``interval`` seconds on a daemon thread until stopped."""

    def __init__(self, heartbeat: Any, interval_seconds: float) -> None:
        self._heartbeat = heartbeat
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="worker-heartbeat", daemon=True)

    def start(self) -> None:
        """Beat once now, then keep beating in the background."""
        self._heartbeat.beat()
        self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._heartbeat.beat()
