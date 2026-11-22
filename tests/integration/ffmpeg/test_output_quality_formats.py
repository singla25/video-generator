"""BL-14: OutputQualityChecker format checks (no expectation) on real tiny clips."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fixtures.quality_clips import make_clip
from vidgen.infrastructure.ffmpeg.quality import OutputQualityChecker

Clip = Callable[..., Path]


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """160x120, 25 fps, H.264, 16 kHz mono AAC, 3 s."""
    return make_clip(tmp_path_factory.mktemp("qt") / "template.mp4")


@pytest.fixture
def clip(tmp_path: Path) -> Clip:
    """Factory writing numbered clips under tmp_path."""
    count = {"n": 0}

    def _make(**kwargs: object) -> Path:
        count["n"] += 1
        return make_clip(tmp_path / f"out{count['n']}.mp4", **kwargs)  # type: ignore[arg-type]

    return _make


@pytest.fixture
def checker() -> OutputQualityChecker:
    """Checker with default tolerances and the real binaries."""
    return OutputQualityChecker(
        ffmpeg_path=shutil.which("ffmpeg") or "ffmpeg", timeout_seconds=120.0
    )


# ---- positive ----------------------------------------------------------------------------


def test_output_equal_to_the_template_passes(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    assert checker.check(template, clip()) == []


def test_unicode_and_emoji_file_names_are_fine(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "राजेश \U0001f3ac 'q'.mp4")
    assert checker.check(template, out) == []


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "issue"),
    [
        ({"size": (320, 240)}, "RESOLUTION_MISMATCH"),
        ({"size": (162, 120)}, "RESOLUTION_MISMATCH"),
        ({"fps": 30}, "FPS_MISMATCH"),
        ({"vcodec": "mpeg4"}, "VIDEO_CODEC_MISMATCH"),
        ({"sample_rate": 44100}, "AUDIO_FORMAT_MISMATCH"),
        ({"channels": 2}, "AUDIO_FORMAT_MISMATCH"),
    ],
)
def test_format_differences_are_reported_by_code(
    checker: OutputQualityChecker, template: Path, clip: Clip, kwargs: dict[str, object], issue: str
) -> None:
    assert issue in checker.check(template, clip(**kwargs))


def test_silent_audio_track_is_reported(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    assert "AUDIO_SILENT" in checker.check(template, clip(audio="silent"))


def test_missing_audio_stream_is_reported_as_an_audio_problem(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    issues = checker.check(template, clip(audio=None))
    assert set(issues) & {"AUDIO_FORMAT_MISMATCH", "AUDIO_SILENT"}


def test_several_problems_are_all_reported(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    issues = checker.check(template, clip(size=(320, 240), fps=30))
    assert {"RESOLUTION_MISMATCH", "FPS_MISMATCH"} <= set(issues)


# ---- edge --------------------------------------------------------------------------------


def test_without_expectation_neither_duration_nor_loudness_is_checked(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    longer_and_louder = clip(seconds=4.0, gain_db=6.0)
    assert checker.check(template, longer_and_louder) == []


def test_issue_codes_are_plain_strings_from_the_enum(
    checker: OutputQualityChecker, template: Path, clip: Clip
) -> None:
    from vidgen.domain.quality import QualityIssue

    issues = checker.check(template, clip(fps=30))
    assert issues
    assert all(issue in {m.value for m in QualityIssue} for issue in issues)


def test_logs_never_contain_file_names(
    checker: OutputQualityChecker,
    template: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    secret_stem = "krishan-secret-name"  # noqa: S105
    bad = make_clip(tmp_path / f"{secret_stem}.mp4", fps=30)
    broken = tmp_path / f"{secret_stem}-broken.mp4"
    broken.write_bytes(b"not a video at all")
    checker.check(template, bad)
    checker.check(template, broken)
    checker.check(template, tmp_path / f"{secret_stem}-missing.mp4")
    assert secret_stem not in caplog.text
    assert str(tmp_path) not in caplog.text
