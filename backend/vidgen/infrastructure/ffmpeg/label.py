"""Renders the bilingual "AI-Generated" band as a PNG with Pillow (AC10, D-10, ADR-004).

Latin runs use the Latin font and Devanagari runs the Devanagari font. Correct Devanagari
shaping (conjuncts, vowel-sign order) needs Pillow's Raqm layout; without it Pillow draws
unshaped glyphs. The renderer never pretends otherwise: ``shaping_available`` tells the
caller, and a warning is logged when it is False.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont, features

from vidgen.domain.codes import DomainError, FailureCode

logger = logging.getLogger(__name__)

LABEL_TEXT = "AI-Generated / एआई-जनित"
BAND_SHARE = 0.10  # the band covers at least this share of the frame height (C2)
BAND_COLOUR = (16, 16, 24)
TEXT_COLOUR = (245, 245, 245)
START_FONT_SHARE = 0.62  # starting font size as a share of the band height
MAX_TEXT_WIDTH_SHARE = 0.94
MAX_INK_HEIGHT_SHARE = 0.90
MIN_FONT_SIZE = 4
_DEVANAGARI_RANGE = range(0x0900, 0x0980)
_JOINERS = frozenset({"‌", "‍"})


def label_band_height(frame_height: int) -> int:
    """Band height in pixels: 10 % of the frame height, rounded up."""
    if frame_height <= 0:
        raise ValueError("frame height must be positive")
    return math.ceil(frame_height * BAND_SHARE - 1e-9)


def _is_devanagari(char: str) -> bool:
    """True for Devanagari letters, signs and joiners."""
    return ord(char) in _DEVANAGARI_RANGE or char in _JOINERS


def split_runs(text: str) -> list[tuple[str, bool]]:
    """Split ``text`` into (run, is_devanagari) pieces.

    Spaces, hyphens and other neutral characters stay with the run before them, so a
    Devanagari word with an inner hyphen is drawn by one font.
    """
    runs: list[tuple[str, bool]] = []
    for char in text:
        neutral = not char.isalpha() and not _is_devanagari(char)
        if runs and (neutral or runs[-1][1] == _is_devanagari(char)):
            runs[-1] = (runs[-1][0] + char, runs[-1][1])
        else:
            runs.append((char, _is_devanagari(char)))
    return runs


@dataclass(frozen=True)
class _Fonts:
    """Both fonts loaded at one size."""

    devanagari: ImageFont.FreeTypeFont
    latin: ImageFont.FreeTypeFont

    def for_run(self, is_devanagari: bool) -> ImageFont.FreeTypeFont:
        """Font used for a run."""
        return self.devanagari if is_devanagari else self.latin


class PillowLabelRenderer:
    """Draws the label text centred on an opaque dark band."""

    def __init__(self, devanagari_font: Path, latin_font: Path, text: str = LABEL_TEXT) -> None:
        self._devanagari_path = devanagari_font
        self._latin_path = latin_font
        self._runs = split_runs(text)

    @property
    def shaping_available(self) -> bool:
        """True when Pillow has Raqm, which Devanagari needs for correct shaping."""
        return bool(features.check("raqm"))

    def render_label(self, width: int, height: int, out: Path) -> None:
        """Write a ``width`` x ``height`` PNG band to ``out``."""
        if width <= 0 or height <= 0:
            raise ValueError("label size must be positive")
        if not self.shaping_available:
            logger.warning("Pillow has no Raqm: Devanagari label text is not shaped")
        fonts = self._fit(width, height)
        image = Image.new("RGB", (width, height), BAND_COLOUR)
        self._draw(ImageDraw.Draw(image), fonts, width, height)
        image.save(out, "PNG")

    def _load(self, size: int) -> _Fonts:
        """Load both fonts at ``size``; any problem is a typed error naming the font."""
        engine = ImageFont.Layout.RAQM if self.shaping_available else ImageFont.Layout.BASIC
        try:
            return _Fonts(
                ImageFont.truetype(str(self._devanagari_path), size, layout_engine=engine),
                ImageFont.truetype(str(self._latin_path), size, layout_engine=engine),
            )
        except OSError as exc:
            raise DomainError(
                FailureCode.INTERNAL_ERROR, "The label font could not be loaded."
            ) from exc

    def _measure(self, fonts: _Fonts) -> tuple[float, float, float]:
        """(total advance, ink top, ink bottom) of the text on a zero baseline."""
        total, top, bottom = 0.0, 0.0, 0.0
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        for run, is_dev in self._runs:
            font = fonts.for_run(is_dev)
            _, run_top, _, run_bottom = probe.textbbox((0, 0), run, font=font, anchor="ls")
            top, bottom = min(top, run_top), max(bottom, run_bottom)
            total += probe.textlength(run, font=font)
        return total, top, bottom

    def _fit(self, width: int, height: int) -> _Fonts:
        """Largest font size whose text fits the band."""
        size = max(MIN_FONT_SIZE, int(height * START_FONT_SHARE))
        while True:
            fonts = self._load(size)
            total, top, bottom = self._measure(fonts)
            fits = (
                total <= width * MAX_TEXT_WIDTH_SHARE
                and bottom - top <= height * MAX_INK_HEIGHT_SHARE
            )
            if fits or size <= MIN_FONT_SIZE:
                return fonts
            size -= 1

    def _draw(self, draw: ImageDraw.ImageDraw, fonts: _Fonts, width: int, height: int) -> None:
        """Draw every run on one baseline, centred horizontally and by ink vertically."""
        total, top, bottom = self._measure(fonts)
        x = (width - total) / 2
        baseline = round(height / 2 - (top + bottom) / 2)
        for run, is_dev in self._runs:
            font = fonts.for_run(is_dev)
            draw.text((x, baseline), run, font=font, fill=TEXT_COLOUR, anchor="ls")
            x += draw.textlength(run, font=font)


if TYPE_CHECKING:  # pragma: no cover
    from vidgen.ports import LabelRenderer

    def _satisfies_port(adapter: PillowLabelRenderer) -> LabelRenderer:
        return adapter
