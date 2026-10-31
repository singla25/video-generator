"""Opt-in model warm-up at worker start (T-PROG-BE, item 6).

CONTRACT
  warm_up_if_enabled(settings, warmables) -> bool in vidgen.worker.warm_up.
  - returns False and calls nothing when warm_up_on_start is off, or ai_mode is not "local"
  - when enabled and local: warm_up() on each warmable once, then release() on each (models
    must not stay in memory), returns True
  - a warmable that raises is logged and skipped; start-up is never crashed
Assumption (flagged): a release() that raises is logged too and the other releases still run.
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


class FakeWarmable:
    """A local model stand-in that writes every call into a shared log."""

    def __init__(
        self,
        name: str,
        log: list[str],
        *,
        fail_warm: Exception | None = None,
        fail_release: Exception | None = None,
    ) -> None:
        self.name = name
        self.log = log
        self.fail_warm = fail_warm
        self.fail_release = fail_release

    def warm_up(self) -> None:
        """Load the model (or fail as configured)."""
        self.log.append(f"{self.name}.warm_up")
        if self.fail_warm is not None:
            raise self.fail_warm

    def release(self) -> None:
        """Free the model (or fail as configured)."""
        self.log.append(f"{self.name}.release")
        if self.fail_release is not None:
            raise self.fail_release


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


def test_enabled_local_warms_every_model_then_releases_them() -> None:
    """P1: all warm_up() calls first, then all release() calls; returns True."""
    log: list[str] = []
    first, second = FakeWarmable("stt", log), FakeWarmable("tts", log)
    assert run(settings(enabled=True), [first, second]) is True
    assert log == ["stt.warm_up", "tts.warm_up", "stt.release", "tts.release"]


def test_each_model_is_warmed_and_released_exactly_once() -> None:
    """P2: no repeats."""
    log: list[str] = []
    run(settings(enabled=True), [FakeWarmable("lipsync", log)])
    assert log.count("lipsync.warm_up") == 1
    assert log.count("lipsync.release") == 1


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize("ai_mode", ["local", "fake"])
def test_disabled_calls_nothing_in_either_mode(ai_mode: str) -> None:
    """N1: the switch off means no model is touched, whatever the mode."""
    log: list[str] = []
    result = run(settings(enabled=False, ai_mode=ai_mode), [FakeWarmable("stt", log)])
    assert result is False
    assert log == []


def test_fake_mode_never_warms_even_when_enabled() -> None:
    """N2: there are no real models in fake mode, so nothing is loaded."""
    log: list[str] = []
    result = run(settings(enabled=True, ai_mode="fake"), [FakeWarmable("stt", log)])
    assert result is False
    assert log == []


def test_a_model_that_fails_to_warm_is_logged_and_the_others_still_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N3: start-up goes on; the healthy model is warmed and released."""
    caplog.set_level(logging.DEBUG)
    log: list[str] = []
    broken = FakeWarmable("stt", log, fail_warm=RuntimeError("weights missing"))
    healthy = FakeWarmable("tts", log)
    assert run(settings(enabled=True), [broken, healthy]) is True
    assert "tts.warm_up" in log and "tts.release" in log
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_release_that_fails_is_logged_and_the_other_releases_still_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N4: a failed release does not stop the rest of the shutdown of models."""
    caplog.set_level(logging.DEBUG)
    log: list[str] = []
    stubborn = FakeWarmable("stt", log, fail_release=OSError("device busy"))
    other = FakeWarmable("tts", log)
    assert run(settings(enabled=True), [stubborn, other]) is True
    assert "tts.release" in log
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


# ---- edge --------------------------------------------------------------------------------


def test_an_empty_list_when_enabled_and_local_returns_true_without_error() -> None:
    """E1: nothing to load is not a failure."""
    assert run(settings(enabled=True), []) is True


def test_warmables_given_as_a_one_shot_iterator_are_all_used() -> None:
    """E2: the function must not depend on walking the input twice."""
    log: list[str] = []
    iterator = iter([FakeWarmable("stt", log), FakeWarmable("tts", log)])
    assert run(settings(enabled=True), iterator) is True
    assert log.count("stt.release") == 1
    assert log.count("tts.release") == 1
