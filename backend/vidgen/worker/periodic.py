"""Run a job once at start and then on a fixed interval, on a daemon thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class PeriodicTask:
    """Calls ``fn`` at start and every ``interval_seconds``; errors are logged, never fatal."""

    def __init__(self, fn: Callable[[], object], interval_seconds: float) -> None:
        self._fn = fn
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="periodic-task", daemon=True)

    def start(self) -> None:
        """Run once now (before returning), then keep running in the background."""
        self._run_once()
        self._thread.start()

    def stop(self) -> None:
        """Stop the loop and wait for the thread, if it was started."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._run_once()

    def _run_once(self) -> None:
        try:
            self._fn()
        except Exception:
            logger.exception("periodic task failed")
