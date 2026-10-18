"""Label PNG renderer: bilingual text on an opaque dark band (AC10, D-10, ADR-004)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.analysis import pixel_mean
from tests.fixtures.assets import devanagari_font
from vidgen.domain.codes import DomainError
from vidgen.infrastructure.ffmpeg.label import LABEL_TEXT, PillowLabelRenderer, label_band_height

DEVANAGARI_PART = "\u090f\u0906\u0908-\u091c\u0928\u093f\u0924"
SIZES = [(320, 24), (1080, 130), (1920, 108), (240, 40), (100, 10)]


def light_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of light (text) pixels, or None if there are none."""
    gray = image.convert("L").point(lambda v: 255 if v > 150 else 0)
    return gray.getbbox()


def render(tmp_path: Path, size: tuple[int, int], text: str | None = None) -> Image.Image:
    """Render a label with the real font (fails the test if the font is absent)."""
    font = devanagari_font()
    renderer = PillowLabelRenderer(font) if text is None else PillowLabelRenderer(font, text=text)
    out = tmp_path / "label.png"
    renderer.render_label(size[0], size[1], out)
    return Image.open(out).convert("RGBA")


# ---- constants and band height --------------------------------------------------------


def test_label_text_is_the_bilingual_disclosure() -> None:
    """TT-AC10-P1 (C2, D-10)."""
    assert LABEL_TEXT == "AI-Generated / " + DEVANAGARI_PART


@pytest.mark.parametrize(("frame_h", "band"), [(1300, 130), (240, 24), (1080, 108), (10, 1)])
def test_band_height_is_ten_percent_of_the_frame_height(frame_h: int, band: int) -> None:
    """TT-AC10-P1, E1."""
    assert label_band_height(frame_h) == band


def test_band_height_is_at_least_ten_percent_for_every_frame_height() -> None:
    """TT-AC10-E2: never below 10 %, never wastefully above 12 %."""
    for height in range(100, 3000, 37):
        band = label_band_height(height)
        assert band >= 0.10 * height - 1e-9
        assert band <= math.ceil(0.12 * height)


@pytest.mark.parametrize("height", [0, -1])
def test_band_height_rejects_nonpositive_frame_height(height: int) -> None:
    """TT-AC10-E2."""
    with pytest.raises(ValueError, match="height"):
        label_band_height(height)


# ---- rendering ------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_png_has_exactly_the_requested_size(tmp_path: Path, size: tuple[int, int]) -> None:
    """TT-AC10-P1 (D-10): full-width band image."""
    assert render(tmp_path, size).size == size


@pytest.mark.parametrize("size", SIZES)
def test_band_is_opaque_and_dark_with_light_text(tmp_path: Path, size: tuple[int, int]) -> None:
    """TT-AC10-P1, E3 (D-10): alpha is 255 everywhere, corners dark, text pixels light."""
    image = render(tmp_path, size)
    width, height = size
    assert image.getchannel("A").getextrema() == (255, 255)
    for corner in [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]:
        assert pixel_mean(image, corner) < 70
    assert light_bbox(image) is not None


@pytest.mark.parametrize("size", SIZES)
def test_text_fits_inside_the_band(tmp_path: Path, size: tuple[int, int]) -> None:
    """TT-AC10-P1: text is neither clipped nor outside the image, and is plausibly large."""
    image = render(tmp_path, size)
    box = light_bbox(image)
    assert box is not None
    left, top, right, bottom = box
    width, height = size
    assert 0 <= left < right <= width
    assert 0 <= top < bottom <= height
    assert (right - left) >= 0.2 * width  # visible, not a speck
    assert (bottom - top) >= 0.25 * height


def test_text_is_horizontally_centred(tmp_path: Path) -> None:
    """TT-AC10-P1."""
    image = render(tmp_path, (1080, 130))
    left, _, right, _ = light_bbox(image) or (0, 0, 0, 0)
    assert abs((left + right) / 2 - 540) < 60


def test_devanagari_part_is_actually_drawn(tmp_path: Path) -> None:
    """TT-AC10-P3 (R2): the right-hand half of the label contains Devanagari glyph pixels."""
    full = render(tmp_path, (1080, 130))
    latin_only = render(tmp_path, (1080, 130), text="AI-Generated /")
    full_box = light_bbox(full)
    latin_box = light_bbox(latin_only)
    assert full_box and latin_box
    assert (full_box[2] - full_box[0]) > (latin_box[2] - latin_box[0]) + 80


def test_devanagari_alone_renders_with_plausible_width(tmp_path: Path) -> None:
    """TT-AC10-P3: a shaped conjunct word is not empty and not absurdly narrow."""
    image = render(tmp_path, (1080, 130), text=DEVANAGARI_PART)
    box = light_bbox(image)
    assert box is not None
    assert 100 <= box[2] - box[0] <= 1080


def test_latin_part_is_drawn_even_if_the_devanagari_font_lacks_latin(tmp_path: Path) -> None:
    """TT-AC10-P1: 'AI-Generated' must not render as blank boxes or nothing."""
    image = render(tmp_path, (1080, 130), text="AI-Generated")
    box = light_bbox(image)
    assert box is not None
    assert box[2] - box[0] >= 150


def test_rendering_is_deterministic(tmp_path: Path) -> None:
    """TT-AC10-P1."""
    first = render(tmp_path, (640, 64)).tobytes()
    second = render(tmp_path, (640, 64)).tobytes()
    assert first == second


# ---- errors ---------------------------------------------------------------------------


def test_missing_font_file_gives_a_clear_typed_error(tmp_path: Path) -> None:
    """TT-AC10-N3."""
    with pytest.raises(DomainError) as info:
        PillowLabelRenderer(tmp_path / "no_such_font.ttf").render_label(320, 24, tmp_path / "l.png")
    assert "font" in info.value.message.lower()


def test_file_that_is_not_a_font_gives_a_typed_error(tmp_path: Path) -> None:
    """TT-AC10-N3."""
    bogus = tmp_path / "bogus.ttf"
    bogus.write_text("this is not a font", encoding="utf-8")
    with pytest.raises(DomainError):
        PillowLabelRenderer(bogus).render_label(320, 24, tmp_path / "l.png")


@pytest.mark.parametrize("size", [(0, 24), (320, 0), (-5, 24), (320, -1)])
def test_nonpositive_sizes_are_rejected(tmp_path: Path, size: tuple[int, int]) -> None:
    """TT-AC10-E2."""
    with pytest.raises(ValueError, match="size"):
        PillowLabelRenderer(devanagari_font()).render_label(size[0], size[1], tmp_path / "l.png")
    assert not (tmp_path / "l.png").exists()
