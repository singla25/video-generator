"""Timing plan: stretch -> absorb -> extend -> fail (AC9, D16). Pure math, seconds."""

from __future__ import annotations

import random

import pytest

from vidgen.domain.codes import FailureCode
from vidgen.domain.timing import (
    NameTooLongToSpeakError,
    SlotTooShortError,
    TimingRules,
    plan_timing,
)

RULES = TimingRules()  # defaults: stretch 0.15, extension 1.5 s, crossfade 30 ms
NO_STRETCH = TimingRules(max_stretch_ratio=0.0)


def test_default_rules_follow_the_spec() -> None:
    """D16, R3.4."""
    assert RULES.max_stretch_ratio == 0.15
    assert RULES.max_extension_s == 1.5
    assert 20 <= RULES.crossfade_ms <= 50


def test_audio_equal_to_slot_needs_no_adjustment() -> None:
    """TT-AC9-P1."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.0, rules=RULES)
    assert plan.stretch_factor == pytest.approx(1.0)
    assert plan.pause_absorbed_s == 0
    assert plan.extension_s == 0
    assert plan.pause_padding_s == 0
    assert plan.duration_delta_s == 0


def test_ten_percent_longer_is_fixed_by_stretch_only() -> None:
    """TT-AC9-P2."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.1, rules=RULES)
    assert plan.stretch_factor == pytest.approx(1.0 / 1.1)
    assert 0.85 <= plan.stretch_factor < 1.0
    assert plan.pause_absorbed_s == 0
    assert plan.extension_s == 0


def test_beyond_stretch_the_pause_absorbs_the_rest() -> None:
    """TT-AC9-P3."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=1.3, rules=RULES)
    assert plan.stretch_factor == pytest.approx(0.85)
    assert plan.pause_absorbed_s == pytest.approx(1.3 * 0.85 - 1.0)
    assert plan.extension_s == 0
    assert plan.duration_delta_s == 0


def test_when_pause_is_not_enough_the_video_is_extended() -> None:
    """TT-AC9-P4."""
    plan = plan_timing(slot_s=1.0, pause_s=0.2, new_audio_s=2.0, rules=RULES)
    assert plan.stretch_factor == pytest.approx(0.85)
    assert plan.pause_absorbed_s == pytest.approx(0.2)
    assert plan.extension_s == pytest.approx(2.0 * 0.85 - 1.0 - 0.2)
    assert plan.duration_delta_s == pytest.approx(plan.extension_s)


def test_shorter_name_pads_the_pause_and_keeps_duration() -> None:
    """TT-AC9-P5."""
    plan = plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=0.7, rules=RULES)
    assert plan.pause_padding_s == pytest.approx(0.3)
    assert plan.stretch_factor == pytest.approx(1.0)
    assert plan.extension_s == 0
    assert plan.duration_delta_s == 0


def test_strategies_apply_in_order_stretch_then_absorb_then_extend() -> None:
    """TT-AC9-P6: a later strategy is used only when the earlier one is exhausted."""
    for new in (1.05, 1.15, 1.25, 1.6, 2.0, 2.2):
        plan = plan_timing(slot_s=1.0, pause_s=0.2, new_audio_s=new, rules=RULES)
        if plan.pause_absorbed_s > 1e-9:
            assert plan.stretch_factor == pytest.approx(0.85)
        if plan.extension_s > 1e-9:
            assert plan.pause_absorbed_s == pytest.approx(0.2)


def test_extension_beyond_the_maximum_fails_with_name_too_long_to_speak() -> None:
    """TT-AC9-N1."""
    with pytest.raises(NameTooLongToSpeakError) as info:
        plan_timing(slot_s=1.0, pause_s=0.2, new_audio_s=3.5, rules=RULES)
    assert info.value.code is FailureCode.NAME_TOO_LONG_TO_SPEAK


def test_stretch_of_exactly_fifteen_percent_uses_no_pause() -> None:
    """TT-AC9-E1."""
    plan = plan_timing(slot_s=1.7, pause_s=1.0, new_audio_s=2.0, rules=RULES)
    assert plan.stretch_factor == pytest.approx(0.85)
    assert plan.pause_absorbed_s == pytest.approx(0.0, abs=1e-9)


def test_just_over_fifteen_percent_starts_using_the_pause() -> None:
    """TT-AC9-E1."""
    plan = plan_timing(slot_s=1.69, pause_s=1.0, new_audio_s=2.0, rules=RULES)
    assert plan.pause_absorbed_s == pytest.approx(0.01)


def test_extension_of_exactly_the_maximum_is_accepted() -> None:
    """TT-AC9-E2."""
    plan = plan_timing(slot_s=1.0, pause_s=0.0, new_audio_s=2.5, rules=NO_STRETCH)
    assert plan.extension_s == pytest.approx(1.5)


def test_extension_one_millisecond_over_the_maximum_fails() -> None:
    """TT-AC9-E2."""
    with pytest.raises(NameTooLongToSpeakError):
        plan_timing(slot_s=1.0, pause_s=0.0, new_audio_s=2.501, rules=NO_STRETCH)


def test_maximum_extension_comes_from_the_rules_argument() -> None:
    """TT-AC9-E3."""
    rules = TimingRules(max_stretch_ratio=0.0, max_extension_s=0.5)
    assert plan_timing(1.0, 0.0, 1.5, rules).extension_s == pytest.approx(0.5)
    with pytest.raises(NameTooLongToSpeakError):
        plan_timing(1.0, 0.0, 1.6, rules)


def test_zero_length_pause_goes_straight_from_stretch_to_extension() -> None:
    """TT-AC9-E4."""
    plan = plan_timing(slot_s=1.0, pause_s=0.0, new_audio_s=1.5, rules=RULES)
    assert plan.pause_absorbed_s == 0
    assert plan.extension_s == pytest.approx(1.5 * 0.85 - 1.0)


def test_slot_shorter_than_two_crossfades_is_rejected() -> None:
    """TT-AC9-E6: no room for a crossfade at both edges."""
    with pytest.raises(SlotTooShortError):
        plan_timing(slot_s=0.05, pause_s=0.5, new_audio_s=0.05, rules=RULES)


@pytest.mark.parametrize("ms", [19, 51, 0, -5, 1000])
def test_crossfade_outside_20_to_50_ms_is_rejected(ms: int) -> None:
    """TT-AC9-N4."""
    with pytest.raises(ValueError, match="crossfade"):
        TimingRules(crossfade_ms=ms)


@pytest.mark.parametrize("ms", [20, 30, 50])
def test_crossfade_inside_20_to_50_ms_is_accepted(ms: int) -> None:
    """TT-AC9-P8 (rule side)."""
    assert TimingRules(crossfade_ms=ms).crossfade_ms == ms


def test_nonpositive_audio_or_slot_length_is_rejected() -> None:
    """TT-AC9-N3 (domain side): zero-length audio never yields a plan."""
    with pytest.raises(ValueError, match="positive"):
        plan_timing(slot_s=1.0, pause_s=0.5, new_audio_s=0.0, rules=RULES)
    with pytest.raises(ValueError, match="positive"):
        plan_timing(slot_s=0.0, pause_s=0.5, new_audio_s=1.0, rules=RULES)


def test_random_inputs_always_give_a_consistent_plan_or_the_documented_failure() -> None:
    """TT-AC9-E10: property-style, fixed seed."""
    rng = random.Random(20261018)  # noqa: S311 - deterministic test data, not security
    for _ in range(2000):
        slot = rng.uniform(0.2, 3.0)
        pause = rng.uniform(0.0, 1.0)
        new = rng.uniform(0.05, 6.0)
        try:
            plan = plan_timing(slot, pause, new, RULES)
        except NameTooLongToSpeakError:
            # Failure only when even maximal stretch + pause + extension cannot fit.
            assert new * 0.85 - slot - pause > RULES.max_extension_s - 1e-9
            continue
        assert 0.85 - 1e-9 <= plan.stretch_factor <= 1.0 + 1e-9
        assert 0 <= plan.pause_absorbed_s <= pause + 1e-9
        assert 0 <= plan.extension_s <= RULES.max_extension_s + 1e-9
        assert plan.pause_padding_s >= 0
        assert plan.duration_delta_s == pytest.approx(plan.extension_s)
        # spoken length = slot + what was absorbed + what was added - what was padded
        spoken = new * plan.stretch_factor
        assert spoken == pytest.approx(
            slot + plan.pause_absorbed_s + plan.extension_s - plan.pause_padding_s, abs=1e-6
        )
        assert plan.final_audio_s == pytest.approx(spoken, abs=1e-6)


def test_float_noise_below_a_nanosecond_gives_no_padding() -> None:
    """Snap: a name 0.5 ns shorter than the slot is the same length for every practical use."""
    plan = plan_timing(slot_s=0.6, pause_s=0.6, new_audio_s=0.6 - 5e-10, rules=RULES)
    assert plan.pause_padding_s == 0.0
    assert plan.extension_s == 0
    assert plan.duration_delta_s == 0


def test_a_gap_above_a_nanosecond_is_real_padding() -> None:
    """Snap boundary: 2 ns of silence is kept, 1 ms certainly."""
    tiny = plan_timing(slot_s=0.6, pause_s=0.6, new_audio_s=0.6 - 2e-9, rules=RULES)
    assert tiny.pause_padding_s == pytest.approx(2e-9, rel=1e-3)
    millisecond = plan_timing(slot_s=0.6, pause_s=0.6, new_audio_s=0.599, rules=RULES)
    assert millisecond.pause_padding_s == pytest.approx(0.001)


def test_padding_is_never_negative_for_a_longer_name() -> None:
    """Snap: longer audio never yields negative padding."""
    plan = plan_timing(slot_s=0.6, pause_s=0.6, new_audio_s=0.6 + 5e-10, rules=RULES)
    assert plan.pause_padding_s == 0.0
