"""Port for the live stage of a preview render (T-PROG-BE).

The worker reports the raw pipeline stage ("fetch", "tts", ...) of a batch's preview; the API
reads it back while the preview is pending. Pure Protocol: no I/O and no framework imports.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class StageReporter(Protocol):
    """Remembers the current preview stage of each batch for a short time."""

    def report(self, batch_id: UUID, stage: str) -> None:
        """Record that the preview of ``batch_id`` has reached raw stage ``stage``."""
        ...

    def current(self, batch_id: UUID) -> str | None:
        """The last reported raw stage of ``batch_id``, or None when there is none."""
        ...

    def clear(self, batch_id: UUID) -> None:
        """Forget the stage of ``batch_id``; clearing a batch with no stage is a no-op."""
        ...
