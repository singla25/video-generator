"""Timing plan for the new name audio: stretch, then absorb pause, then extend (AC8, AC9, D16)."""

from __future__ import annotations

from dataclasses import dataclass

from vidgen.domain.codes import DomainError, FailureCode

MS_PER_SECOND = 1000
MIN_CROSSFADE_MS = 20
MAX_CROSSFADE_MS = 50
# Float noise allowance when comparing seconds computed through multiplication.
EPSILON_S = 1e-9


class NameTooLongToSpeakError(DomainError):
    """Even with maximal stretch, pause and extension the name does not fit."""

    def __init__(self) -> None:
        super().__init__(FailureCode.NAME_TOO_LONG_TO_SPEAK)


class SlotTooShortError(DomainError):
    """The slot cannot hold a crossfade at both edges (D-1)."""

    def __init__(self) -> None:
        super().__init__(FailureCode.SLOT_NOT_FOUND, "The marked part of the video is too short.")


@dataclass(frozen=True)
class TimingRules:
    """Timing limits (from settings)."""

    max_stretch_ratio: float = 0.15
    max_extension_s: float = 1.5
    crossfade_ms: int = 30

    def __post_init__(self) -> None:
        """Reject a crossfade outside 20-50 ms."""
        if not MIN_CROSSFADE_MS <= self.crossfade_ms <= MAX_CROSSFADE_MS:
            raise ValueError(
                f"crossfade must be {MIN_CROSSFADE_MS}-{MAX_CROSSFADE_MS} ms, "
                f"got {self.crossfade_ms}"
            )

    @property
    def crossfade_s(self) -> float:
        """Crossfade length in seconds."""
        return self.crossfade_ms / MS_PER_SECOND


@dataclass(frozen=True)
class TimingPlan:
    """How the new audio fits into the slot. All lengths in seconds."""

    stretch_factor: float
    pause_absorbed_s: float
    extension_s: float
    pause_padding_s: float
    final_audio_s: float

    @property
    def duration_delta_s(self) -> float:
        """Change of the video length versus the template (D16)."""
        return self.extension_s


def plan_timing(
    slot_s: float, pause_s: float, new_audio_s: float, rules: TimingRules
) -> TimingPlan:
    """Fit ``new_audio_s`` into the slot, using the pause after it and then extending the video.

    Speech is only ever sped up (never slowed down); a shorter name pads the pause (D-2).
    """
    if slot_s <= 0 or new_audio_s <= 0:
        raise ValueError("slot and audio lengths must be positive")
    if slot_s < 2 * rules.crossfade_s:
        raise SlotTooShortError
    # Compress just enough to fit, but never beyond the allowed ratio; never slow down.
    stretch = min(1.0, max(slot_s / new_audio_s, 1.0 - rules.max_stretch_ratio))
    spoken_s = new_audio_s * stretch
    overflow_s = max(0.0, spoken_s - slot_s)
    absorbed_s = min(overflow_s, pause_s)
    extension_s = overflow_s - absorbed_s
    if extension_s > rules.max_extension_s + EPSILON_S:
        raise NameTooLongToSpeakError
    return TimingPlan(
        stretch_factor=stretch,
        pause_absorbed_s=absorbed_s,
        extension_s=extension_s,
        pause_padding_s=max(0.0, slot_s - spoken_s),
        final_audio_s=spoken_s,
    )


def duration_within_tolerance(
    actual_s: float, template_s: float, delta_s: float, tolerance_ms: int
) -> bool:
    """True if the output length equals template + delta within the tolerance (AC8)."""
    expected_s = template_s + delta_s
    return abs(actual_s - expected_s) <= tolerance_ms / MS_PER_SECOND + EPSILON_S


def expected_frame_count(duration_s: float, fps: float) -> int:
    """Number of frames for ``duration_s`` at ``fps``, rounded to the nearest frame."""
    return round(duration_s * fps)
