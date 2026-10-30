"""Name gap after the new name (DD-34): the video grows by gap_s, the timing rules do not change."""

from __future__ import annotations

import pytest

from vidgen.domain import timing
from vidgen.domain.timing import (
    NameTooLongToSpeakError,
    TimingPlan,
    TimingRules,
    duration_within_tolerance,
    plan_timing,
)

RULES = TimingRules()  # defaults: stretch 0.15, extension 1.5 s, crossfade 30 ms
NO_STRETCH = TimingRules(max_stretch_ratio=0.0)
GAP_S = 0.25


def test_timing_plan_gap_defaults_to_zero_for_old_constructions() -> None:
    """DD-34: gap_s is declared last with a default, so five-field constructions still work."""
    plan = TimingPlan(1.0, 0.0, 0.0, 0.0, 1.0)
    assert plan.gap_s == 0.0
    assert plan.duration_delta_s == 0.0


def test_gap_zero_leaves_every_field_as_before() -> None:
    """DD-34 default: slot 1.0, pause 0.5, name 1.3 gives the same timing as today."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.3, rules=RULES)
    assert plan.stretch_factor == pytest.approx(0.85)
    assert plan.pause_absorbed_s == pytest.approx(1.3 * 0.85 - 1.0)
    assert plan.extension_s == 0
    assert plan.pause_padding_s == 0
    assert plan.final_audio_s == pytest.approx(1.3 * 0.85)
    assert plan.gap_s == 0.0
    assert plan.duration_delta_s == plan.extension_s


def test_explicit_zero_gap_is_the_same_plan_as_the_default() -> None:
    """DD-34 default: passing gap_s=0.0 changes nothing at all."""
    default = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.3, rules=RULES)
    explicit = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.3, rules=RULES, gap_s=0.0)
    assert explicit == default


@pytest.mark.parametrize(
    ("pause", "new"),
    [(0.5, 0.9), (0.5, 1.0), (0.5, 1.3), (0.2, 2.0), (0.0, 1.5)],
)
def test_gap_changes_only_the_gap_field(pause: float, new: float) -> None:
    """DD-34: the gap never changes stretch, absorbed pause, extension or padding."""
    base = plan_timing(slot_s=1.0, pause_s=pause, new_audio_s=new, rules=RULES)
    gapped = plan_timing(slot_s=1.0, pause_s=pause, new_audio_s=new, rules=RULES, gap_s=GAP_S)
    assert gapped.stretch_factor == base.stretch_factor
    assert gapped.pause_absorbed_s == base.pause_absorbed_s
    assert gapped.extension_s == base.extension_s
    assert gapped.pause_padding_s == base.pause_padding_s
    assert gapped.final_audio_s == base.final_audio_s
    assert gapped.gap_s == GAP_S


def test_shorter_name_with_gap_grows_the_video_by_the_gap_only() -> None:
    """DD-34 positive: slot 1.0, pause 0.5, name 0.9, gap 0.25 -> pad 0.1, grow by 0.25."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=0.9, rules=RULES, gap_s=GAP_S)
    assert plan.extension_s == 0
    assert plan.gap_s == pytest.approx(0.25)
    assert plan.duration_delta_s == pytest.approx(0.25)
    assert plan.pause_padding_s == pytest.approx(0.1)


@pytest.mark.parametrize(("pause", "new"), [(0.5, 1.3), (0.2, 2.0)])
def test_gap_adds_to_the_extension_for_a_long_name(pause: float, new: float) -> None:
    """DD-34 positive: a name longer than the slot grows by extension + gap."""
    base = plan_timing(slot_s=1.0, pause_s=pause, new_audio_s=new, rules=RULES)
    plan = plan_timing(slot_s=1.0, pause_s=pause, new_audio_s=new, rules=RULES, gap_s=GAP_S)
    assert plan.duration_delta_s == pytest.approx(base.extension_s + GAP_S)


def test_gap_never_causes_name_too_long_to_speak() -> None:
    """DD-34 negative: a name that is too long with gap 0 is too long with gap 0.25 too."""
    with pytest.raises(NameTooLongToSpeakError):
        plan_timing(slot_s=1.0, pause_s=0.0, new_audio_s=3.5, rules=RULES)
    with pytest.raises(NameTooLongToSpeakError):
        plan_timing(slot_s=1.0, pause_s=0.0, new_audio_s=3.5, rules=RULES, gap_s=GAP_S)


def test_a_name_that_fits_without_gap_still_fits_with_the_maximum_gap() -> None:
    """DD-34 edge: the gap is not counted against max_extension_s (extension exactly 1.5 s)."""
    assert plan_timing(1.0, 0.0, 2.5, NO_STRETCH).extension_s == pytest.approx(1.5)
    max_gap = timing.MAX_GAP_S
    plan = plan_timing(1.0, 0.0, 2.5, NO_STRETCH, gap_s=max_gap)
    assert plan.extension_s == pytest.approx(1.5)
    assert plan.gap_s == max_gap


def test_max_gap_is_one_second() -> None:
    """DD-34: the module constant that bounds the gap."""
    assert timing.MAX_GAP_S == 1.0


@pytest.mark.parametrize("gap", [-0.1, -1e-6, 1.0001, 2.0])
def test_gap_outside_zero_to_one_second_is_rejected(gap: float) -> None:
    """DD-34 negative: a negative gap or one above 1.0 s raises ValueError."""
    with pytest.raises(ValueError):
        plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=0.9, rules=RULES, gap_s=gap)


@pytest.mark.parametrize("gap", [0.0, 0.25, 1.0])
def test_gap_inside_zero_to_one_second_is_accepted(gap: float) -> None:
    """DD-34 positive and edge: 0.0 and exactly 1.0 are allowed."""
    assert plan_timing(1.0, 0.5, 0.9, RULES, gap_s=gap).gap_s == gap


def test_output_length_with_gap_is_template_plus_gap_within_40_ms() -> None:
    """DD-34 positive: 4.25 s output for a 4.0 s template with gap 0.25 passes at 40 ms."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=0.9, rules=RULES, gap_s=GAP_S)
    assert duration_within_tolerance(
        actual_s=4.25, template_s=4.0, delta_s=plan.duration_delta_s, tolerance_ms=40
    )
    assert not duration_within_tolerance(
        actual_s=4.0, template_s=4.0, delta_s=plan.duration_delta_s, tolerance_ms=40
    )
