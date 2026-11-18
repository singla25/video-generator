"""Ports for render providers: per-queue worker heartbeats."""

from __future__ import annotations

from typing import Protocol


class QueueHeartbeats(Protocol):
    """Tells whether a worker is alive on a queue (AC2); workers report in with ``beat``."""

    def beat(self, queue: str) -> None:
        """A worker on ``queue`` reports in."""
        ...

    def is_alive(self, queue: str) -> bool:
        """True while a worker is alive on ``queue``."""
        ...
