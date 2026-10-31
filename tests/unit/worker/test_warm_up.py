"""Opt-in model warm-up at worker start (T-PROG-BE, item 6).

CONTRACT
  warm_up_if_enabled(settings, warmables) -> bool in vidgen.worker.warm_up.
  - returns False and calls nothing when warm_up_on_start is off, or ai_mode is not "local"
  - when enabled and local, one model at a time: for each warmable in order, warm_up() and then
    release() before the next one is touched (w1.warm_up, w1.release, w2.warm_up, w2.release, ...).
    Never more than one model is resident at any moment. Returns True
  - warm_up() that raises: logged, release() is still attempted best-effort, then the next model
  - release() that raises: logged, the next model still runs
  - no exception ever leaves the function; start-up is never crashed
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from typing import Any

import pytest
from pydantic import SecretStr

from vidgen.settings import Settings
from vidgen.worker.warm_up import warm_up_if_enabled


class ModelTracker:
    """Shared record of every warm_up/release call and of how many models are resident."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.resident: set[str] = set()
        self.peak = 0

    def loaded(self, name: str) -> None:
        """A model's weights are now in memory."""
        self.log.append(f"{name}.warm_up")
        self.resident.add(name)
        self.peak = max(self.peak, len(self.resident))

    def freed(self, name: str) -> None:
        """A model's weights are no longer in memory."""
        self.log.append(f"{name}.release")
        self.resident.discard(name)


class FakeWarmable:
    """A local model stand-in that reports every call to a shared tracker."""

    def __init__(
        self,
        name: str,
        tracker: ModelTracker,
        *,
        fail_warm: Exception | None = None,
        fail_release: Exception | None = None,
    ) -> None:
        self.name = name
        self.tracker = tracker
        self.fail_warm = fail_warm
        self.fail_release = fail_release

    def warm_up(self) -> None:
        """Load the model (or fail as configured)."""
        if self.fail_warm is not None:
            self.tracker.log.append(f"{self.name}.warm_up")
            raise self.fail_warm
        self.tracker.loaded(self.name)

    def release(self) -> None:
        """Free the model (or fail as configured)."""
        if self.fail_release is not None:
            self.tracker.log.append(f"{self.name}.release")
            raise self.fail_release
        self.tracker.freed(self.name)


def settings(*, enabled: bool, ai_mode: str = "local") -> Settings:
    """Settings with throwaway secrets and the warm-up switch set as given."""
    return Settings(
        creator_entity="Test Creator Org",
        encryption_key=SecretStr(secrets.token_hex(32)),
        index_key=SecretStr(secrets.token_hex(32)),
        session_secret=SecretStr(secrets.token_hex(32)),
        admin_password_hash=SecretStr("x"),
        warm_up_on_start=enabled,
        ai_mode=ai_mode,  # type: ignore[arg-type]
    )


def run(config: Settings, warmables: Iterable[Any]) -> bool:
    """Call the function under test."""
    return warm_up_if_enabled(config, warmables)


# ---- positive ----------------------------------------------------------------------------


def test_enabled_local_warms_and_releases_one_model_before_the_next() -> None:
    """P1: w1.warm_up, w1.release, w2.warm_up, w2.release; returns True."""
    tracker = ModelTracker()
    first, second = FakeWarmable("stt", tracker), FakeWarmable("tts", tracker)
    assert run(settings(enabled=True), [first, second]) is True
    assert tracker.log == ["stt.warm_up", "stt.release", "tts.warm_up", "tts.release"]


def test_each_model_is_warmed_and_released_exactly_once() -> None:
    """P2: no repeats."""
    tracker = ModelTracker()
    run(settings(enabled=True), [FakeWarmable("lipsync", tracker)])
    assert tracker.log.count("lipsync.warm_up") == 1
    assert tracker.log.count("lipsync.release") == 1


def test_never_more_than_one_model_is_resident_at_a_time() -> None:
    """P3: the peak number of loaded models is one, and none is left in memory afterwards."""
    tracker = ModelTracker()
    models = [FakeWarmable(name, tracker) for name in ("stt", "tts", "lipsync")]
    assert run(settings(enabled=True), models) is True
    assert tracker.peak == 1
    assert tracker.resident == set()


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize("ai_mode", ["local", "fake"])
def test_disabled_calls_nothing_in_either_mode(ai_mode: str) -> None:
    """N1: the switch off means no model is touched, whatever the mode."""
    tracker = ModelTracker()
    result = run(settings(enabled=False, ai_mode=ai_mode), [FakeWarmable("stt", tracker)])
    assert result is False
    assert tracker.log == []


def test_fake_mode_never_warms_even_when_enabled() -> None:
    """N2: there are no real models in fake mode, so nothing is loaded."""
    tracker = ModelTracker()
    result = run(settings(enabled=True, ai_mode="fake"), [FakeWarmable("stt", tracker)])
    assert result is False
    assert tracker.log == []


def test_a_model_that_fails_to_warm_is_released_then_the_next_one_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N3: the broken model is logged and released best-effort; start-up goes on."""
    caplog.set_level(logging.DEBUG)
    tracker = ModelTracker()
    broken = FakeWarmable("stt", tracker, fail_warm=RuntimeError("weights missing"))
    healthy = FakeWarmable("tts", tracker)
    assert run(settings(enabled=True), [broken, healthy]) is True
    assert tracker.log == ["stt.warm_up", "stt.release", "tts.warm_up", "tts.release"]
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_release_that_fails_is_logged_and_the_next_model_still_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N4: a failed release does not stop the models after it."""
    caplog.set_level(logging.DEBUG)
    tracker = ModelTracker()
    stubborn = FakeWarmable("stt", tracker, fail_release=OSError("device busy"))
    other = FakeWarmable("tts", tracker)
    assert run(settings(enabled=True), [stubborn, other]) is True
    assert tracker.log == ["stt.warm_up", "stt.release", "tts.warm_up", "tts.release"]
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_model_whose_warm_up_and_release_both_fail_does_not_stop_the_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N5: both steps of one model fail; both are logged and the next model is still warmed."""
    caplog.set_level(logging.DEBUG)
    tracker = ModelTracker()
    doomed = FakeWarmable(
        "stt",
        tracker,
        fail_warm=RuntimeError("weights missing"),
        fail_release=OSError("device busy"),
    )
    healthy = FakeWarmable("tts", tracker)
    assert run(settings(enabled=True), [doomed, healthy]) is True
    assert tracker.log == ["stt.warm_up", "stt.release", "tts.warm_up", "tts.release"]
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) >= 2


# ---- edge --------------------------------------------------------------------------------


def test_an_empty_list_when_enabled_and_local_returns_true_without_error() -> None:
    """E1: nothing to load is not a failure."""
    assert run(settings(enabled=True), []) is True


def test_warmables_given_as_a_one_shot_iterator_are_all_used() -> None:
    """E2: the function must not depend on walking the input twice."""
    tracker = ModelTracker()
    iterator = iter([FakeWarmable("stt", tracker), FakeWarmable("tts", tracker)])
    assert run(settings(enabled=True), iterator) is True
    assert tracker.log.count("stt.release") == 1
    assert tracker.log.count("tts.release") == 1


def test_a_failing_last_model_still_returns_true_and_leaves_nothing_resident() -> None:
    """E3: the last model failing to warm is the edge of the loop; nothing stays loaded."""
    tracker = ModelTracker()
    first = FakeWarmable("stt", tracker)
    last = FakeWarmable("tts", tracker, fail_warm=RuntimeError("weights missing"))
    assert run(settings(enabled=True), [first, last]) is True
    assert tracker.log == ["stt.warm_up", "stt.release", "tts.warm_up", "tts.release"]
    assert tracker.resident == set()
