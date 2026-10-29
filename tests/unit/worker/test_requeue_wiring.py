"""L10(d): settings and the periodic runner for requeue_stuck_rows.

EXPECTED API
  Settings.stuck_after_seconds: int = 600 (gt 0)
  Settings.requeue_interval_seconds: float = 300 (gt 0)
  vidgen.worker.periodic.PeriodicTask(fn, interval_seconds)
      start() runs fn once at once, then every interval on a daemon thread; stop() joins;
      an exception in fn is logged and never stops the loop.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.integration.api.conftest import make_settings
from vidgen.worker.periodic import PeriodicTask

URL = "postgresql+psycopg://vidgen:devpassword@127.0.0.1:5432/vidgen_test"


def test_defaults(tmp_path: Path) -> None:
    settings = make_settings(URL, tmp_path)
    assert settings.stuck_after_seconds == 600
    assert settings.requeue_interval_seconds == 300


@pytest.mark.parametrize("field", ["stuck_after_seconds", "requeue_interval_seconds"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_values_are_rejected(tmp_path: Path, field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(URL, tmp_path, **{field: value})


def test_runs_once_at_start_then_on_the_interval_and_not_after_stop() -> None:
    ticks = threading.Semaphore(0)
    count = 0

    def work() -> None:
        nonlocal count
        count += 1
        ticks.release()

    task = PeriodicTask(work, 0.01)
    task.start()
    assert ticks.acquire(timeout=2)  # the immediate run
    assert ticks.acquire(timeout=2)  # at least one interval run
    task.stop()
    seen = count
    threading.Event().wait(0.05)
    assert count == seen


def test_the_first_run_happens_before_start_returns() -> None:
    calls: list[int] = []
    task = PeriodicTask(lambda: calls.append(1), 60)
    task.start()
    try:
        assert calls == [1]
    finally:
        task.stop()


def test_an_error_in_the_job_is_logged_and_the_loop_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    ticks = threading.Semaphore(0)
    calls = 0

    def work() -> None:
        nonlocal calls
        calls += 1
        ticks.release()
        raise RuntimeError("boom")

    task = PeriodicTask(work, 0.01)
    task.start()
    assert ticks.acquire(timeout=2)
    assert ticks.acquire(timeout=2)
    task.stop()
    assert calls >= 2
    assert any("boom" in r.getMessage() or r.exc_info for r in caplog.records)


def test_stop_without_start_is_safe() -> None:
    PeriodicTask(lambda: None, 1).stop()
