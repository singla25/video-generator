"""Plain data types exchanged through the ports. Pure: no I/O imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SheetRow:
    """A non-blank data row; ``row_number`` is the sheet row (the header is row 1)."""

    row_number: int
    cells: list[str]


@dataclass(frozen=True)
class VideoLimits:
    """Accepted ranges for an uploaded video (from settings); bounds are inclusive."""

    max_bytes: int
    max_seconds: float
    min_seconds: float


@dataclass(frozen=True)
class VideoInfo:
    """Facts about an accepted video. Tags and other metadata are deliberately left out."""

    container: str
    video_codec: str
    audio_codec: str
    width: int
    height: int
    fps: float
    duration_s: float
    size_bytes: int

    @property
    def has_audio(self) -> bool:
        """True when an audio track exists (always true for an accepted video)."""
        return bool(self.audio_codec)
