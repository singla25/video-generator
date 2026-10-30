"""Bubble label: a small "AI" badge at the bottom-right of a transparent frame (DD-32, DD-36).

LS-R-*. The look inside the bubble (tint, ring, text, shadow) is in test_bubble_look.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.analysis import pixel_mean
from tests.fixtures.assets import devanagari_font, latin_font
from tests.fixtures.bubble import render_bubble
from vidgen.domain.codes import DomainError
from vidgen.infrastructure.ffmpeg.label import (
    PillowBubbleRenderer,
    PillowLabelRenderer,
    bubble_box,
    bubble_diameter,
    build_label_renderer,
)

SIZES = [(320, 240), (1080, 1920), (1080, 1300), (3840, 2160), (321, 241), (64, 64), (240, 426)]
DARK = 70


# ---- geometry -------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_bubble_box_is_48_per_1080_wide_with_12_per_1080_margin(size: tuple[int, int]) -> None:
    """LS-R-P2 (DD-36): square box, side 48/1080 of the width, 12/1080 from right and bottom."""
    width, height = size
    left, top, right, bottom = bubble_box(width, height)
    side = round(width * 48 / 1080)
    margin = round(width * 12 / 1080)
    assert bubble_diameter(width) == right - left == bottom - top == side
    assert width - right == margin
    assert height - bottom == margin
    assert 0 <= left < right <= width
    assert 0 <= top < bottom <= height


@pytest.mark.parametrize("width", [1, 2, 10, 33])
def test_bubble_diameter_is_at_least_one_pixel(width: int) -> None:
    """LS-R-E3."""
    assert bubble_diameter(width) >= 1


def test_bubble_diameter_grows_with_the_frame_width() -> None:
    """LS-R-E3."""
    widths = [100, 320, 720, 1080, 2160]
    sizes = [bubble_diameter(w) for w in widths]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == len(sizes)


# ---- rendering ------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_png_is_exactly_the_frame_size_and_has_alpha(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P1: overlaid at 0:0 it adds no height and needs no placement."""
    image = render_bubble(tmp_path, size)
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize("size", SIZES[:4])
def test_everything_outside_the_bubble_box_is_transparent(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-P3 (DD-36): alpha is 0 everywhere outside the box, not just nearby."""
    image = render_bubble(tmp_path, size)
    left, top, right, bottom = bubble_box(*size)
    ink = image.getchannel("A").getbbox()
    assert ink is not None, "the bubble is empty"
    # getbbox is exclusive on the right and bottom; every drawn pixel lies inside the box.
    assert ink[0] >= left and ink[1] >= top
    assert ink[2] <= right and ink[3] <= bottom


@pytest.mark.parametrize("size", SIZES[:4])
def test_bubble_box_corners_are_see_through(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P3 (DD-36): the four corners of the box are outside the circle, so alpha 0."""
    image = render_bubble(tmp_path, size)
    left, top, right, bottom = bubble_box(*size)
    corners = [(left, top), (right - 1, top), (left, bottom - 1), (right - 1, bottom - 1)]
    for xy in corners:
        assert image.getpixel(xy)[3] == 0, f"corner {xy} is drawn"  # type: ignore[index]


def test_band_renderer_is_unchanged(tmp_path: Path) -> None:
    """LS-R-P5: the band is still a full-width opaque dark image."""
    out = tmp_path / "band.png"
    PillowLabelRenderer(devanagari_font(), latin_font()).render_label(320, 24, out)
    with Image.open(out) as image:
        rgba = image.convert("RGBA")
    assert rgba.size == (320, 24)
    assert rgba.getchannel("A").getextrema() == (255, 255)
    assert pixel_mean(rgba, (0, 0)) < DARK


# ---- errors ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(0, 240), (320, 0), (-1, 10), (10, -5)])
def test_non_positive_size_is_rejected_without_a_file(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-N1."""
    out = tmp_path / "bubble.png"
    with pytest.raises(ValueError, match="size"):
        PillowBubbleRenderer(latin_font=latin_font()).render_label(size[0], size[1], out)
    assert not out.exists()


def test_missing_font_is_a_typed_error_and_leaves_no_file(tmp_path: Path) -> None:
    """LS-R-N2."""
    out = tmp_path / "bubble.png"
    with pytest.raises(DomainError):
        PillowBubbleRenderer(latin_font=tmp_path / "nope.ttf").render_label(320, 240, out)
    assert not out.exists()


# ---- factory --------------------------------------------------------------------------


def test_factory_returns_the_renderer_for_the_style() -> None:
    """LS-R-E2."""
    fonts = {"devanagari_font": devanagari_font(), "latin_font": latin_font()}
    assert isinstance(build_label_renderer("bubble", **fonts), PillowBubbleRenderer)
    assert isinstance(build_label_renderer("band", **fonts), PillowLabelRenderer)


@pytest.mark.parametrize("style", ["", "stripe", "BAND"])
def test_factory_rejects_an_unknown_style(style: str) -> None:
    """LS-R-E2."""
    with pytest.raises(ValueError, match="label_style"):
        build_label_renderer(style, devanagari_font=devanagari_font(), latin_font=latin_font())
