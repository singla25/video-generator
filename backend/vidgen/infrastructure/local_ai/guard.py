"""One heavy render at a time: a second one is refused instead of exhausting memory (AC7)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from vidgen.infrastructure.local_ai.errors import AiBusyError


class SingleRenderGuard:
    """A non-blocking, process-wide lock around the memory-heavy models."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Hold the guard; raise ``AiBusyError`` at once if it is taken. Always released."""
        if not self._lock.acquire(blocking=False):
            raise AiBusyError("another AI render is already running; try again when it ends")
        try:
            yield
        finally:
            self._lock.release()
