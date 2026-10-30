"""Bubble label: a small "AI" badge at the bottom-right of a transparent frame (DD-32). LS-R-*."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.analysis import pixel_mean
from tests.fixtures.assets import devanagari_font, latin_font
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
LIGHT = 150
MIN_CONTRAST = 7.0


def render(tmp_path: Path, size: tuple[int, int]) -> Image.Image:
    """Render the bubble overlay with the real Latin font."""
    out = tmp_path / "bubble.png"
    PillowBubbleRenderer(latin_font=latin_font()).render_label(size[0], size[1], out)
    return Image.open(out).convert("RGBA")


def luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance."""

    def channel(value: int) -> float:
        s = value / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---- geometry -------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_bubble_box_is_about_nine_percent_wide_with_three_percent_margin(
    size: tuple[int, int],
) -> None:
    """LS-R-P2."""
    width, height = size
    left, top, right, bottom = bubble_box(width, height)
    assert bubble_diameter(width) == right - left == bottom - top
    assert abs((right - left) - 0.09 * width) <= 1.5
    assert abs((width - right) - 0.03 * width) <= 1.5
    assert abs((height - bottom) - 0.03 * width) <= 1.5
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
    image = render(tmp_path, size)
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize("size", SIZES[:4])
def test_everything_outside_the_bubble_box_is_transparent(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-P3: only the bottom-right corner carries pixels."""
    image = render(tmp_path, size)
    left, top, right, bottom = bubble_box(*size)
    alpha = image.getchannel("A")
    ink = alpha.getbbox()
    assert ink is not None, "the bubble is empty"
    assert ink[0] >= left - 1 and ink[1] >= top - 1
    assert ink[2] <= right + 1 and ink[3] <= bottom + 1


@pytest.mark.parametrize("size", SIZES[:4])
def test_bubble_is_a_rounded_opaque_dark_disc(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P3: corners of the box are see-through, the body is opaque and dark."""
    image = render(tmp_path, size)
    left, top, right, bottom = bubble_box(*size)
    d = right - left
    assert image.getpixel((left, top))[3] == 0  # type: ignore[index]
    assert image.getpixel((right - 1, bottom - 1))[3] == 0  # type: ignore[index]
    inside = (left + max(2, d // 8), top + d // 2)
    assert image.getpixel(inside)[3] == 255  # type: ignore[index]
    assert pixel_mean(image, inside) < DARK


@pytest.mark.parametrize("size", SIZES[:4])
def test_text_is_light_centred_and_has_enough_contrast(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-P4: "AI" is legible on the dark fill."""
    image = render(tmp_path, size)
    left, top, right, bottom = bubble_box(*size)
    d = right - left
    pixels = image.load()
    assert pixels is not None
    light = [
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if pixels[x, y][3] == 255 and sum(pixels[x, y][:3]) / 3 > LIGHT
    ]
    assert light, "no light text pixels"
    xs, ys = [p[0] for p in light], [p[1] for p in light]
    assert (max(xs) - min(xs)) >= 0.25 * d  # not a speck
    assert (max(ys) - min(ys)) >= 0.25 * d
    assert abs((min(xs) + max(xs)) / 2 - (left + right) / 2) <= 0.12 * d
    assert abs((min(ys) + max(ys)) / 2 - (top + bottom) / 2) <= 0.12 * d
    brightest = max((pixels[x, y][:3] for x, y in light), key=sum)
    fill = pixels[left + max(2, d // 8), top + d // 2][:3]
    ratio = (luminance(brightest) + 0.05) / (luminance(fill) + 0.05)
    assert ratio >= MIN_CONTRAST


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
