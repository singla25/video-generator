"""Issue codes reported by the output quality check (AC8, AC9). Pure: no I/O imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class QualityIssue(StrEnum):
    """One way a rendered output can differ from its template; the value equals the name."""

    DURATION_MISMATCH = "DURATION_MISMATCH"
    RESOLUTION_MISMATCH = "RESOLUTION_MISMATCH"
    FPS_MISMATCH = "FPS_MISMATCH"
    VIDEO_CODEC_MISMATCH = "VIDEO_CODEC_MISMATCH"
    AUDIO_FORMAT_MISMATCH = "AUDIO_FORMAT_MISMATCH"
    AUDIO_SILENT = "AUDIO_SILENT"
    LOUDNESS_MISMATCH = "LOUDNESS_MISMATCH"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    UNREADABLE_OUTPUT = "UNREADABLE_OUTPUT"


@dataclass(frozen=True)
class SlotRegion:
    """One name slot as (start, end) seconds in the template and in the rendered output."""

    template: tuple[float, float]
    output: tuple[float, float]


@dataclass(frozen=True)
class OutputExpectation:
    """What a rendered output should look like: length change and where each slot sits."""

    delta_s: float
    regions: tuple[SlotRegion, ...]
