"""BL-14: build_quality_checker, temp-cleanup settings and job. No database, no network."""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from vidgen.infrastructure.fakes import FakeQualityChecker
from vidgen.infrastructure.ffmpeg.quality import OutputQualityChecker
from vidgen.settings import Settings
from vidgen.worker.runner import build_quality_checker, build_temp_cleanup_job

HOUR = 3600


def make(tmp_path: Path, **overrides: object) -> Settings:
    """Settings with throwaway secrets, storage under ``tmp_path``."""
    values: dict[str, object] = {
        "creator_entity": "Test Creator Org",
        "encryption_key": SecretStr(secrets.token_hex(32)),
        "index_key": SecretStr(secrets.token_hex(32)),
        "session_secret": SecretStr(secrets.token_hex(32)),
        "admin_password_hash": SecretStr("x"),
        "storage_root": tmp_path / "media",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def age(path: Path, seconds: float) -> None:
    """Make ``path`` look ``seconds`` old."""
    then = time.time() - seconds
    os.utime(path, (then, then))


# ---- build_quality_checker ----------------------------------------------------------------


def test_fake_mode_gets_the_fake_checker(tmp_path: Path) -> None:
    assert isinstance(build_quality_checker(make(tmp_path, ai_mode="fake")), FakeQualityChecker)


@pytest.mark.parametrize("mode", ["local", "modal"])
def test_other_modes_get_the_real_checker_with_settings_tolerances(
    tmp_path: Path, mode: str
) -> None:
    settings = make(tmp_path, ai_mode=mode, duration_tolerance_ms=120, loudness_tolerance_lu=0.5)
    checker = build_quality_checker(settings)
    assert isinstance(checker, OutputQualityChecker)
    assert not isinstance(checker, FakeQualityChecker)
    # Behavioural proof of the wiring: a missing file is reported, not raised.
    assert checker.check(tmp_path / "a.mp4", tmp_path / "b.mp4") == ["UNREADABLE_OUTPUT"]


# ---- settings ----------------------------------------------------------------------------


def test_temp_settings_defaults(tmp_path: Path) -> None:
    settings = make(tmp_path)
    assert settings.temp_cleanup_interval_seconds == 3600.0
    assert settings.temp_max_age_seconds == 3600.0


@pytest.mark.parametrize("field", ["temp_cleanup_interval_seconds", "temp_max_age_seconds"])
@pytest.mark.parametrize("value", [0, -1, -0.5])
def test_non_positive_temp_settings_are_rejected(tmp_path: Path, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        make(tmp_path, **{field: value})


# ---- build_temp_cleanup_job ---------------------------------------------------------------


def test_job_removes_old_temp_files_and_keeps_fresh_and_normal_files(tmp_path: Path) -> None:
    settings = make(tmp_path, temp_max_age_seconds=HOUR)
    root = settings.storage_root
    (root / "batch").mkdir(parents=True)
    old, fresh = root / "batch" / ".tmp-old", root / ".tmp-fresh"
    normal, old_normal = root / "batch" / "out.mp4", root / "old.mp4"
    for path in (old, fresh, normal, old_normal):
        path.write_bytes(b"x")
    age(old, 2 * HOUR)
    age(old_normal, 2 * HOUR)

    job = build_temp_cleanup_job(settings)

    assert job() == 1
    assert not old.exists()
    assert fresh.exists() and normal.exists() and old_normal.exists()


def test_job_returns_zero_when_nothing_is_stale_and_is_repeatable(tmp_path: Path) -> None:
    settings = make(tmp_path)
    settings.storage_root.mkdir(parents=True)
    job = build_temp_cleanup_job(settings)
    assert job() == 0
    assert job() == 0


def test_job_uses_the_configured_max_age(tmp_path: Path) -> None:
    settings = make(tmp_path, temp_max_age_seconds=60)
    settings.storage_root.mkdir(parents=True)
    stale = settings.storage_root / ".tmp-x"
    stale.write_bytes(b"x")
    age(stale, 120)
    assert build_temp_cleanup_job(settings)() == 1


# The main() wiring (PeriodicTask(build_temp_cleanup_job(...), temp_cleanup_interval_seconds)
# started next to the requeue task) has no seam in the worker tests: check manually that the
# worker log shows the cleanup running at start-up and that stop() joins it.
