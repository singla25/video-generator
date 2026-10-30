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
from vidgen.domain.validation import ZWJ, ZWNJ

logger = logging.getLogger(__name__)

LABEL_TEXT = "AI-Generated / एआई-जनित"
BAND_SHARE = 0.10  # the band covers at least this share of the frame height (C2)
BAND_COLOUR = (16, 16, 24)
TEXT_COLOUR = (245, 245, 245)
START_FONT_SHARE = 0.62  # starting font size as a share of the band height
MAX_TEXT_WIDTH_SHARE = 0.94
MAX_INK_HEIGHT_SHARE = 0.90
MIN_FONT_SIZE = 4
BUBBLE_DIAMETER_SHARE = 0.09  # bubble diameter as a share of the frame width (DD-32)
BUBBLE_MARGIN_SHARE = 0.03  # distance from the right and bottom edges, share of the width
BUBBLE_TEXT = "AI"
BUBBLE_TEXT_SHARE = 0.46  # starting font size as a share of the bubble diameter
BUBBLE_MAX_INK_SHARE = 0.62  # the text ink may use at most this share of the diameter
LABEL_STYLES = ("bubble", "band")
_DEVANAGARI_RANGE = range(0x0900, 0x0980)
_JOINERS = frozenset({ZWJ, ZWNJ})


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


def bubble_diameter(frame_width: int) -> int:
    """Bubble diameter in pixels: about 9 % of the frame width, at least 1."""
    return max(1, round(frame_width * BUBBLE_DIAMETER_SHARE))


def bubble_box(frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the bubble, in the bottom-right corner."""
    margin = round(frame_width * BUBBLE_MARGIN_SHARE)
    size = bubble_diameter(frame_width)
    right, bottom = frame_width - margin, frame_height - margin
    return right - size, bottom - size, right, bottom


class PillowBubbleRenderer:
    """Draws a small dark round badge with light text on a transparent full-size frame."""

    def __init__(self, latin_font: Path, text: str = BUBBLE_TEXT) -> None:
        self._latin_path = latin_font
        self._text = text

    def render_label(self, width: int, height: int, out: Path) -> None:
        """Write a transparent ``width`` x ``height`` PNG with the bubble to ``out``."""
        if width <= 0 or height <= 0:
            raise ValueError("label size must be positive")
        box = bubble_box(width, height)
        diameter = box[2] - box[0]
        font = self._fit(diameter)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((box[0], box[1], box[2] - 1, box[3] - 1), fill=(*BAND_COLOUR, 255))
        centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        draw.text(centre, self._text, font=font, fill=(*TEXT_COLOUR, 255), anchor="mm")
        image.save(out, "PNG")

    def _fit(self, diameter: int) -> ImageFont.FreeTypeFont:
        """Largest font whose text fits inside the bubble."""
        size = max(MIN_FONT_SIZE, int(diameter * BUBBLE_TEXT_SHARE))
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        while True:
            try:
                font = ImageFont.truetype(str(self._latin_path), size)
            except OSError as exc:
                raise DomainError(
                    FailureCode.INTERNAL_ERROR, "The label font could not be loaded."
                ) from exc
            left, top, right, bottom = probe.textbbox((0, 0), self._text, font=font)
            fits = max(right - left, bottom - top) <= diameter * BUBBLE_MAX_INK_SHARE
            if fits or size <= MIN_FONT_SIZE:
                return font
            size -= 1


def build_label_renderer(
    style: str, devanagari_font: Path, latin_font: Path
) -> PillowLabelRenderer | PillowBubbleRenderer:
    """The renderer for a label style; an unknown style is an error, never a fallback."""
    if style == "bubble":
        return PillowBubbleRenderer(latin_font)
    if style == "band":
        return PillowLabelRenderer(devanagari_font, latin_font)
    raise ValueError(f"unknown label_style {style!r}; use one of {LABEL_STYLES}")


if TYPE_CHECKING:  # pragma: no cover
    from vidgen.ports import LabelRenderer

    def _satisfies_port(adapter: PillowLabelRenderer) -> LabelRenderer:
        return adapter
