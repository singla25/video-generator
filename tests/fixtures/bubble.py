"""Shared helpers for the see-through AI bubble tests (DD-36)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from tests.fixtures.assets import latin_font
from vidgen.infrastructure.ffmpeg.label import PillowBubbleRenderer


def render_bubble(tmp_path: Path, size: tuple[int, int]) -> Image.Image:
    """Render the bubble overlay for a frame of ``size`` with the real Latin font."""
    out = tmp_path / "bubble.png"
    PillowBubbleRenderer(latin_font=latin_font()).render_label(size[0], size[1], out)
    return Image.open(out).convert("RGBA")
