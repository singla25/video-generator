"""BL-14: OutputQualityChecker never raises for bad media or a missing tool."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from tests.fixtures.media import make_audio_only_mp4, truncate_copy
from tests.fixtures.quality_clips import make_clip
from vidgen.domain.timing import expected_output
from vidgen.infrastructure.ffmpeg.quality import OutputQualityChecker
from vidgen.ports.models import OutputExpectation

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
NO_CHANGE = OutputExpectation(delta_s=0.0, regions=())


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A good 3 s template."""
    return make_clip(tmp_path_factory.mktemp("qb") / "template.mp4")


@pytest.fixture
def checker() -> OutputQualityChecker:
    """Checker with the real binaries."""
    return OutputQualityChecker(ffmpeg_path=FFMPEG, timeout_seconds=120.0)


@pytest.mark.parametrize("expected", [None, NO_CHANGE])
def test_zero_byte_output_is_empty_output(
    checker: OutputQualityChecker,
    template: Path,
    tmp_path: Path,
    expected: OutputExpectation | None,
) -> None:
    out = tmp_path / "zero.mp4"
    out.write_bytes(b"")
    assert checker.check(template, out, expected) == ["EMPTY_OUTPUT"]


def test_garbage_bytes_with_a_video_extension_are_unreadable(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    out = tmp_path / "garbage.mp4"
    out.write_bytes(bytes(range(256)) * 40)
    assert checker.check(template, out) == ["UNREADABLE_OUTPUT"]


def test_truncated_file_is_unreadable(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    out = truncate_copy(make_clip(tmp_path / "full.mp4"), tmp_path / "cut.mp4", 0.3)
    assert checker.check(template, out) == ["UNREADABLE_OUTPUT"]


def test_missing_output_is_unreadable_not_an_exception(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    assert checker.check(template, tmp_path / "nope.mp4") == ["UNREADABLE_OUTPUT"]


def test_file_without_a_video_stream_is_reported(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    out = make_audio_only_mp4(tmp_path / "audio.mp4", seconds=3.0)
    assert checker.check(template, out)  # not "OK": some issue code, no exception


def test_wrong_extension_with_real_content_is_judged_by_content(
    checker: OutputQualityChecker, template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "real.bin")
    assert checker.check(template, out) == []


def test_unreadable_template_is_reported_not_raised(
    checker: OutputQualityChecker, tmp_path: Path
) -> None:
    good = make_clip(tmp_path / "good.mp4")
    result = checker.check(tmp_path / "missing-template.mp4", good)
    assert result and all(isinstance(code, str) for code in result)


def test_missing_ffprobe_binary_gives_unreadable_without_leaking_the_path(
    template: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    tool = str(tmp_path / "no-such-dir-xyz" / "ffprobe")
    broken = OutputQualityChecker(ffmpeg_path=FFMPEG, ffprobe_path=tool)
    out = make_clip(tmp_path / "ok.mp4")
    assert broken.check(template, out) == ["UNREADABLE_OUTPUT"]
    assert "no-such-dir-xyz" not in caplog.text


def test_missing_ffmpeg_binary_does_not_crash_a_loudness_check(
    template: Path, tmp_path: Path
) -> None:
    broken = OutputQualityChecker(ffmpeg_path=str(tmp_path / "no-ffmpeg"))
    out = make_clip(tmp_path / "ok.mp4")
    expected = expected_output([(1.0, 2.0)], [_plan()])
    result = broken.check(template, out, expected)
    assert isinstance(result, list)


def _plan() -> object:
    from vidgen.domain.timing import TimingPlan

    return TimingPlan(1.0, 0.0, 0.0, 0.0, 1.0)
