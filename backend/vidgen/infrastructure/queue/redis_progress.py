"""Preview stage progress on Redis: one expiring key per batch (T-PROG-BE).

The key expires on its own, so a stage left behind by a crashed worker disappears after the TTL.
Redis errors are raised to the caller; the render service and the API decide what they mean.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

DEFAULT_TTL_SECONDS = 900  # longer than any preview render; a crashed worker's stage expires
KEY_PREFIX = "vidgen:stage:"


def stage_key(batch_id: UUID) -> str:
    """The Redis key of a batch's stage: the prefix plus the id in its usual text form."""
    return f"{KEY_PREFIX}{batch_id}"


class RedisStageReporter:
    """``StageReporter`` backed by one expiring Redis key per batch."""

    def __init__(self, client: Any, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._client = client
        self._ttl = ttl_seconds

    def report(self, batch_id: UUID, stage: str) -> None:
        """Store the stage and restart its time to live."""
        self._client.set(stage_key(batch_id), stage, ex=self._ttl)

    def current(self, batch_id: UUID) -> str | None:
        """The stored stage, or None when the key is missing or has expired."""
        raw: bytes | str | None = self._client.get(stage_key(batch_id))
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    def clear(self, batch_id: UUID) -> None:
        """Delete the stage key; a missing key is not an error."""
        self._client.delete(stage_key(batch_id))
