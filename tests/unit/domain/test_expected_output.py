"""BL-14: QualityIssue codes and the expected output timeline (expected_output)."""

from __future__ import annotations

import dataclasses

import pytest

from vidgen.domain.quality import QualityIssue
from vidgen.domain.timing import TimingPlan, expected_output
from vidgen.ports.models import OutputExpectation, SlotRegion

ISSUES = [
    "DURATION_MISMATCH",
    "RESOLUTION_MISMATCH",
    "FPS_MISMATCH",
    "VIDEO_CODEC_MISMATCH",
    "AUDIO_FORMAT_MISMATCH",
    "AUDIO_SILENT",
    "LOUDNESS_MISMATCH",
    "EMPTY_OUTPUT",
    "UNREADABLE_OUTPUT",
]


def plan(*, absorbed: float = 0.0, extension: float = 0.0, gap: float = 0.0) -> TimingPlan:
    """A plan with only the fields that matter for the timeline."""
    return TimingPlan(
        stretch_factor=1.0,
        pause_absorbed_s=absorbed,
        extension_s=extension,
        pause_padding_s=0.0,
        final_audio_s=1.0,
        gap_s=gap,
    )


# ---- positive ----------------------------------------------------------------------------


def test_quality_issue_has_exactly_the_agreed_members_with_value_equal_name() -> None:
    assert [m.name for m in QualityIssue] == ISSUES
    assert all(m.value == m.name and str(m) == m.name for m in QualityIssue)


def test_one_slot_with_extension_and_gap() -> None:
    result = expected_output([(1.0, 2.0)], [plan(absorbed=0.2, extension=0.5, gap=0.1)])
    assert result.delta_s == pytest.approx(0.6)
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.template == pytest.approx((1.0, 2.2))
    assert region.output == pytest.approx((1.0, 1.0 + 1.0 + 0.2 + 0.5 + 0.1))


def test_two_slots_shift_the_second_output_region_by_the_first_delta() -> None:
    plans = [plan(extension=0.4, gap=0.1), plan(absorbed=0.3, extension=0.2)]
    result = expected_output([(1.0, 2.0), (4.0, 5.0)], plans)
    assert result.delta_s == pytest.approx(0.7)
    first, second = result.regions
    assert first.template == pytest.approx((1.0, 2.0))
    assert first.output == pytest.approx((1.0, 2.5))
    assert second.template == pytest.approx((4.0, 5.3))
    assert second.output == pytest.approx((4.5, 4.5 + 1.0 + 0.3 + 0.2))


def test_result_is_a_tuple_of_slot_regions() -> None:
    result = expected_output([(1.0, 2.0)], [plan()])
    assert isinstance(result, OutputExpectation)
    assert isinstance(result.regions, tuple)
    assert isinstance(result.regions[0], SlotRegion)


# ---- negative ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slots", "plans"),
    [
        ([(1.0, 2.0)], []),
        ([], [plan()]),
        ([(1.0, 2.0), (4.0, 5.0)], [plan()]),
        ([(1.0, 2.0)], [plan(), plan()]),
    ],
)
def test_mismatched_lengths_of_slots_and_plans_raise_value_error(
    slots: list[tuple[float, float]], plans: list[TimingPlan]
) -> None:
    with pytest.raises(ValueError):
        expected_output(slots, plans)


def test_expectation_and_region_are_frozen() -> None:
    result = expected_output([(1.0, 2.0)], [plan()])
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.delta_s = 1.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.regions[0].output = (0.0, 1.0)  # type: ignore[misc]


# ---- edge --------------------------------------------------------------------------------


def test_zero_delta_keeps_output_regions_on_the_template_slots() -> None:
    result = expected_output([(1.0, 2.0), (4.0, 5.0)], [plan(), plan()])
    assert result.delta_s == 0
    assert [r.output for r in result.regions] == [(1.0, 2.0), (4.0, 5.0)]
    assert [r.template for r in result.regions] == [(1.0, 2.0), (4.0, 5.0)]


def test_absorbed_pause_alone_changes_regions_but_not_the_delta() -> None:
    result = expected_output([(1.0, 2.0), (4.0, 5.0)], [plan(absorbed=0.3), plan()])
    assert result.delta_s == 0
    assert result.regions[0].template == pytest.approx((1.0, 2.3))
    assert result.regions[0].output == pytest.approx((1.0, 2.3))
    assert result.regions[1].output == pytest.approx((4.0, 5.0))
