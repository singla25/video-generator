"""The look of the see-through AI bubble (DD-36): size, tint, white ring, text, soft shadow.

LS-R-P6..P10. Geometry of the box and transparency outside it are in test_bubble_renderer.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.bubble import render_bubble
from vidgen.infrastructure.ffmpeg.label import bubble_box, bubble_diameter

# Bubbles of at least 48 px: the look is pinned at real sizes (320 px is too small for the text).
BIG = [(1080, 1920), (1080, 1300), (3840, 2160)]
PRODUCTION = [(1080, 1920), (1080, 1300)]
RING_SHARE = 0.04
TINT_ROW_SHARE = 0.18
TEXT_MIN_PIXELS = 20
TEXT_CLEARANCE = 4
TEXT_CENTRE_TOLERANCE = 2
TEXT_MAX_HEIGHT_SHARE = 0.6
SHADOW_ALPHA = 60
SHADOW_MAX_CHANNEL = 40
SHADOW_REACH = 3


@dataclass(frozen=True)
class Disc:
    """The bubble's box and circle, in pixel and continuous coordinates."""

    left: int
    top: int
    right: int
    bottom: int
    diameter: int
    cx: float
    cy: float
    radius: float
    ring: int


def disc_of(size: tuple[int, int]) -> Disc:
    """Geometry of the bubble for a frame of ``size``; the ring is max(1, round(0.04 d))."""
    left, top, right, bottom = bubble_box(*size)
    diameter = right - left
    return Disc(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        diameter=diameter,
        cx=(left + right) / 2,
        cy=(top + bottom) / 2,
        radius=diameter / 2,
        ring=max(1, round(RING_SHARE * diameter)),
    )


def distance(x: int, y: int, disc: Disc) -> float:
    """Distance from a pixel centre to the circle centre."""
    return math.hypot(x + 0.5 - disc.cx, y + 0.5 - disc.cy)


def is_white(pixel: tuple[int, int, int, int], floor: int) -> bool:
    """Opaque enough and every colour channel at least ``floor``."""
    r, g, b, a = pixel
    return a >= 200 and min(r, g, b) >= floor


def text_pixels(image: Image.Image, disc: Disc) -> list[tuple[int, int]]:
    """White text pixels: strictly inside the circle and 4 px clear of the ring."""
    pixels = image.load()
    assert pixels is not None
    inner = disc.radius - disc.ring - TEXT_CLEARANCE
    return [
        (x, y)
        for y in range(disc.top, disc.bottom)
        for x in range(disc.left, disc.right)
        if is_white(pixels[x, y], 240) and distance(x, y, disc) <= inner
    ]


def shadow_pixels(image: Image.Image, disc: Disc) -> list[tuple[int, int]]:
    """Dark, fairly opaque pixels inside the circle: candidates for the text shadow."""
    pixels = image.load()
    assert pixels is not None
    found = []
    for y in range(disc.top, disc.bottom):
        for x in range(disc.left, disc.right):
            r, g, b, a = pixels[x, y]
            if (
                a >= SHADOW_ALPHA
                and max(r, g, b) <= SHADOW_MAX_CHANNEL
                and distance(x, y, disc) < disc.radius
            ):
                found.append((x, y))
    return found


# ---- geometry worked examples ---------------------------------------------------------


@pytest.mark.parametrize(
    ("width", "diameter", "margin"),
    [(1080, 48, 12), (320, 14, 4), (1920, 85, 21)],
)
def test_bubble_diameter_and_margin_match_the_dd36_examples(
    width: int, diameter: int, margin: int
) -> None:
    """LS-R-P6 (DD-36): 48/1080 of the width across, 12/1080 from the right and bottom."""
    height = 2 * width
    left, top, right, bottom = bubble_box(width, height)
    assert bubble_diameter(width) == diameter
    assert right - left == bottom - top == diameter
    assert width - right == margin
    assert height - bottom == margin


# ---- look inside the disc -------------------------------------------------------------


@pytest.mark.parametrize("size", BIG)
def test_bubble_body_is_a_faint_black_tint(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P7 (DD-36): the disc is see-through: alpha 30-50, near-black, above the text."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    x = (disc.left + disc.right) // 2
    y = disc.top + round(TINT_ROW_SHARE * disc.diameter)
    r, g, b, a = image.getpixel((x, y))  # type: ignore[misc]
    assert 30 <= a <= 50, f"tint alpha {a} at {(x, y)}"
    assert max(r, g, b) <= 20, f"tint colour {(r, g, b)} at {(x, y)} is not near-black"


@pytest.mark.parametrize("size", PRODUCTION)
def test_bubble_ring_is_white_and_two_pixels_thick_at_1080(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-P8 (DD-36): ring = max(1, round(0.04 d)) = 2 px at 48 px, white, on the top edge."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    assert disc.ring == 2
    x = (disc.left + disc.right) // 2
    pixels = image.load()
    assert pixels is not None
    for y in (disc.top, disc.top + 1):
        r, g, b, a = pixels[x, y]
        assert a >= 200 and min(r, g, b) >= 235, f"ring pixel {(x, y)} is {(r, g, b, a)}"
    assert not is_white(pixels[x, disc.top + disc.ring + 1], 235), "ring is thicker than 2 px"


@pytest.mark.parametrize("size", BIG)
def test_bubble_edge_is_anti_aliased(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P9 (DD-36): the outer edge has partly transparent pixels, not a hard stair step."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    pixels = image.load()
    assert pixels is not None
    edge = [
        (x, y)
        for y in range(disc.top, disc.bottom)
        for x in range(disc.left, disc.right)
        if disc.radius - 1 <= distance(x, y, disc) <= disc.radius + 1 and 1 < pixels[x, y][3] < 254
    ]
    assert edge, "no partly transparent pixel on the outer edge"


@pytest.mark.parametrize("size", BIG)
def test_text_ai_is_white_and_inside_the_ring(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P4 (DD-36): at least 20 white "AI" pixels, inside the ring with 4 px clearance."""
    image = render_bubble(tmp_path, size)
    found = text_pixels(image, disc_of(size))
    assert len(found) >= TEXT_MIN_PIXELS, f"only {len(found)} white text pixels"


@pytest.mark.parametrize("size", BIG)
def test_text_ai_is_centred_in_the_bubble(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P4 (DD-36): the text's bounding box centre is within 2 px of the circle centre."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    found = text_pixels(image, disc)
    assert found, "no white text pixels"
    xs = [x for x, _ in found]
    ys = [y for _, y in found]
    # Pixel indices to continuous coordinates: a pixel x covers [x, x + 1).
    centre_x = (min(xs) + max(xs) + 1) / 2
    centre_y = (min(ys) + max(ys) + 1) / 2
    assert abs(centre_x - disc.cx) <= TEXT_CENTRE_TOLERANCE, f"x centre {centre_x} vs {disc.cx}"
    assert abs(centre_y - disc.cy) <= TEXT_CENTRE_TOLERANCE, f"y centre {centre_y} vs {disc.cy}"


@pytest.mark.parametrize("size", BIG)
def test_text_ai_is_at_most_0_6_of_the_diameter_tall(tmp_path: Path, size: tuple[int, int]) -> None:
    """LS-R-P4 (DD-36): the text's bounding box is at most 0.6 of the bubble diameter tall."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    found = text_pixels(image, disc)
    assert found, "no white text pixels"
    ys = [y for _, y in found]
    height = max(ys) - min(ys) + 1
    assert height <= TEXT_MAX_HEIGHT_SHARE * disc.diameter, f"text is {height} px tall"


@pytest.mark.parametrize("size", PRODUCTION)
def test_text_has_a_soft_dark_shadow_within_three_pixels(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    """LS-R-P10 (DD-36): a dark, fairly opaque pixel inside the disc lies within 3 px of text."""
    image = render_bubble(tmp_path, size)
    disc = disc_of(size)
    text = text_pixels(image, disc)
    assert text, "no white text pixels"
    near = [
        (x, y)
        for x, y in shadow_pixels(image, disc)
        if any(math.hypot(x - tx, y - ty) <= SHADOW_REACH for tx, ty in text)
    ]
    assert near, "no soft shadow next to the text"
