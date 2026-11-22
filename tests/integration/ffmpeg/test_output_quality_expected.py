"""BL-14: OutputQualityChecker duration and loudness checks against an expectation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.fixtures.quality_clips import make_clip
from vidgen.domain.timing import TimingPlan, expected_output
from vidgen.infrastructure.ffmpeg.quality import OutputQualityChecker
from vidgen.ports.models import OutputExpectation

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SLOT = (1.0, 2.0)


def plan(extension: float = 0.0, gap: float = 0.0) -> TimingPlan:
    """A plan that only extends the video."""
    return TimingPlan(1.0, 0.0, extension, 0.0, 1.0, gap_s=gap)


def checker(**kwargs: float) -> OutputQualityChecker:
    """Checker with the real binaries and optional tolerances."""
    return OutputQualityChecker(ffmpeg_path=FFMPEG, timeout_seconds=120.0, **kwargs)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3 s template; steady tone, slot 1-2 s."""
    return make_clip(tmp_path_factory.mktemp("qe") / "template.mp4")


def same() -> OutputExpectation:
    """No change in length."""
    return expected_output([SLOT], [plan()])


# ---- positive ----------------------------------------------------------------------------


def test_output_equal_to_the_template_passes_with_an_expectation(
    template: Path, tmp_path: Path
) -> None:
    assert checker().check(template, make_clip(tmp_path / "o.mp4"), same()) == []


def test_output_longer_by_the_expected_delta_passes(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", seconds=3.5)
    expected = expected_output([SLOT], [plan(extension=0.4, gap=0.1)])
    assert expected.delta_s == pytest.approx(0.5)
    assert checker().check(template, out, expected) == []


def test_multi_slot_expectation_passes_when_every_region_matches(
    template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "o.mp4", seconds=3.6, gain_region=(1.0, 3.6))
    long_template = make_clip(tmp_path / "t.mp4", seconds=3.0, gain_region=(0.0, 3.0))
    expected = expected_output([(0.5, 1.0), (2.0, 2.5)], [plan(0.3), plan(0.3)])
    assert checker().check(long_template, out, expected) == []


def test_half_an_lu_difference_in_the_slot_region_passes(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=0.5)
    assert checker().check(template, out, same()) == []


# ---- negative ----------------------------------------------------------------------------


def test_duration_off_by_200_ms_is_reported(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", seconds=3.2)
    assert "DURATION_MISMATCH" in checker().check(template, out, same())


def test_unexpected_length_change_is_reported_when_nothing_was_planned(
    template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "o.mp4", seconds=3.5)
    assert "DURATION_MISMATCH" in checker().check(template, out, same())


def test_two_lu_louder_in_the_slot_region_is_a_loudness_mismatch(
    template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=2.0)
    assert checker().check(template, out, same()) == ["LOUDNESS_MISMATCH"]


def test_two_lu_quieter_in_the_slot_region_is_a_loudness_mismatch(
    template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=-2.0)
    assert "LOUDNESS_MISMATCH" in checker().check(template, out, same())


def test_loudness_outside_the_slot_is_not_compared(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=6.0, gain_region=(2.2, 3.0))
    assert checker().check(template, out, same()) == []


def test_silent_output_with_an_expectation_reports_silence(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", audio="silent")
    assert "AUDIO_SILENT" in checker().check(template, out, same())


def test_second_region_of_a_multi_slot_expectation_is_checked(
    template: Path, tmp_path: Path
) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=3.0, gain_region=(2.0, 2.5))
    expected = expected_output([(0.5, 1.0), (2.0, 2.5)], [plan(), plan()])
    assert "LOUDNESS_MISMATCH" in checker().check(template, out, expected)


# ---- edge --------------------------------------------------------------------------------


def test_duration_tolerance_boundary(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", seconds=3.2)  # 200 ms off
    assert checker(duration_tolerance_ms=250).check(template, out, same()) == []
    assert "DURATION_MISMATCH" in checker(duration_tolerance_ms=150).check(template, out, same())


def test_loudness_tolerance_boundary(template: Path, tmp_path: Path) -> None:
    out = make_clip(tmp_path / "o.mp4", gain_db=1.5)
    assert checker(loudness_tolerance_lu=2.0).check(template, out, same()) == []
    assert "LOUDNESS_MISMATCH" in checker(loudness_tolerance_lu=1.0).check(template, out, same())


def test_default_tolerances_are_50_ms_and_one_lu(template: Path, tmp_path: Path) -> None:
    default = OutputQualityChecker(ffmpeg_path=FFMPEG)
    near = make_clip(tmp_path / "near.mp4", gain_db=0.8)
    assert default.check(template, near, same()) == []
    far = make_clip(tmp_path / "far.mp4", gain_db=1.5)
    assert "LOUDNESS_MISMATCH" in default.check(template, far, same())


def test_empty_region_list_checks_only_duration(template: Path, tmp_path: Path) -> None:
    louder = make_clip(tmp_path / "o.mp4", gain_db=6.0)
    assert checker().check(template, louder, OutputExpectation(0.0, ())) == []


def test_quiet_template_region_is_skipped_so_a_loud_output_is_not_a_mismatch(
    tmp_path: Path,
) -> None:
    """Nothing to compare with where the template itself is silent (edge)."""
    quiet_template = make_clip(tmp_path / "t.mp4", audio="silent")
    out = make_clip(tmp_path / "o.mp4", gain_db=12.0)
    assert checker().check(quiet_template, out, same()) == []
