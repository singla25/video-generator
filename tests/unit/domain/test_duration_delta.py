"""Output duration check (AC8). Cases TT-AC8-N2, E3, E4."""

from __future__ import annotations

import pytest

from vidgen.domain.timing import duration_within_tolerance, expected_frame_count


def test_duration_equal_to_template_plus_delta_passes() -> None:
    """TT-AC8-P4, E3: delta 0."""
    assert duration_within_tolerance(actual_s=4.0, template_s=4.0, delta_s=0.0, tolerance_ms=50)


def test_duration_with_positive_delta_passes() -> None:
    """TT-AC8-P4."""
    assert duration_within_tolerance(actual_s=4.5, template_s=4.0, delta_s=0.5, tolerance_ms=50)


@pytest.mark.parametrize("actual", [4.45, 4.55])
def test_duration_exactly_at_the_tolerance_boundary_passes(actual: float) -> None:
    """TT-AC8-E3: +/-50 ms inclusive."""
    assert duration_within_tolerance(actual_s=actual, template_s=4.0, delta_s=0.5, tolerance_ms=50)


@pytest.mark.parametrize("actual", [4.44, 4.56, 3.0, 9.0])
def test_duration_beyond_tolerance_fails(actual: float) -> None:
    """TT-AC8-N2."""
    assert not duration_within_tolerance(
        actual_s=actual, template_s=4.0, delta_s=0.5, tolerance_ms=50
    )


def test_tolerance_comes_from_the_argument() -> None:
    """TT-AC8-E3."""
    assert duration_within_tolerance(actual_s=4.08, template_s=4.0, delta_s=0.0, tolerance_ms=100)
    assert not duration_within_tolerance(
        actual_s=4.08, template_s=4.0, delta_s=0.0, tolerance_ms=50
    )


@pytest.mark.parametrize(
    ("duration", "fps", "frames"),
    [(4.0, 60.0, 240), (4.0, 25.0, 100), (1.001, 30000 / 1001, 30), (0.0, 25.0, 0)],
)
def test_expected_frame_count_rounds_to_nearest_frame(
    duration: float, fps: float, frames: int
) -> None:
    """TT-AC8-E4: 60, 25 and 29.97 fps."""
    assert expected_frame_count(duration, fps) == frames
