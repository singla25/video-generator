"""Pure value types shared by the domain and the ports. No I/O imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    """A transcribed word with its time span in seconds."""

    text: str
    start_s: float
    end_s: float
    confidence: float


@dataclass(frozen=True)
class TextRegion:
    """On-screen text found in a video: what, when and where (pixels)."""

    text: str
    start_s: float
    end_s: float
    x: int
    y: int
    w: int
    h: int
    confidence: float
