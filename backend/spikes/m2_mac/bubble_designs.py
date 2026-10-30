"""Bubble design previews (DD-35): three small AI badges drawn on one real frame.

Usage (repository root, after a timing render has written a ``*_G.mp4``):

    PYTHONPATH=backend .venv/bin/python backend/spikes/m2_mac/bubble_designs.py

Outputs go to ``work/local_out/bubble_designs/`` (git-ignored): ``full_A/B/C.png`` (whole frame),
``zoom_old.png`` (the current bubble) and ``zoom_*.png`` crops, stacked in ``sheet.png``.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[3]
TIMING_DIR = ROOT / "backend" / "spikes" / "m2_mac" / "work" / "local_out" / "timing"
OUT_DIR = ROOT / "backend" / "spikes" / "m2_mac" / "work" / "local_out" / "bubble_designs"
FONT_DIR = ROOT / "backend" / "vidgen" / "assets" / "fonts"
BOLD_FONT = FONT_DIR / "NotoSans-Bold.ttf"
DEVANAGARI_FONT = FONT_DIR / "NotoSansDevanagari-Bold.ttf"

FRAME_T_S = 20.0
FRAME_WIDTH = 1080
FRAME_HEIGHT = 1300
DIAMETER = round(0.05 * FRAME_WIDTH)  # 54 px
PAD_PX = 4  # margin around the circle inside the drawn patch, for the soft shadow
PATCH_PX = DIAMETER + 2 * PAD_PX
MARGIN = round(0.015 * FRAME_WIDTH)  # 16 px from the right and bottom edges
TEXT = "AI"
TEXT_SHARE = 0.5  # font size as a share of the diameter
SUPERSAMPLE = 4  # draw at 4x, then downscale with LANCZOS for smooth edges
SHADOW_OFFSET_PX = 1
SHADOW_BLUR_PX = 1
ZOOM_BOX = (760, 1130, 1080, 1300)  # x0, y0, x1, y1 of the zoomed crop
ZOOM = 3
SHEET_GAP_PX = 8
SHEET_BACKGROUND = (128, 128, 128)

RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class Design:
    """Colours and effects of one bubble design; RGBA values are 0-255."""

    name: str
    fill: RGBA
    ring_px: float
    ring: RGBA
    text: RGBA
    shadow: RGBA | None  # None means no text shadow


DESIGNS: tuple[Design, ...] = (
    Design(
        "A",
        fill=(255, 255, 255, 90),
        ring_px=2.0,
        ring=(255, 255, 255, 220),
        text=(255, 255, 255, 255),
        shadow=(0, 0, 0, 90),
    ),
    Design(
        "B",
        fill=(0, 0, 0, 40),
        ring_px=2.0,
        ring=(255, 255, 255, 230),
        text=(255, 255, 255, 255),
        shadow=(0, 0, 0, 120),
    ),
    Design(
        "C",
        fill=(0, 0, 0, 90),
        ring_px=1.5,
        ring=(255, 255, 255, 200),
        text=(255, 255, 255, 255),
        shadow=None,
    ),
)


def bubble_box() -> tuple[int, int, int, int]:
    """Left, top, right, bottom of the circle in the bottom-right corner of the frame."""
    right, bottom = FRAME_WIDTH - MARGIN, FRAME_HEIGHT - MARGIN
    return right - DIAMETER, bottom - DIAMETER, right, bottom


def find_timing_video() -> Path:
    """The first ``*_G.mp4`` timing render; a clear error when none has been made yet."""
    matches = sorted(TIMING_DIR.glob("*_G.mp4"))
    if not matches:
        raise FileNotFoundError(
            f"no *_G.mp4 in {TIMING_DIR}; run the timing render for variant G first"
        )
    return matches[0]


def extract_frame(video: Path, out: Path) -> Image.Image:
    """Decode one frame at ``FRAME_T_S`` with ffmpeg and return it as an RGBA image."""
    command = [
        "ffmpeg", "-v", "error", "-y", "-i", str(video),
        "-ss", f"{FRAME_T_S:.1f}", "-frames:v", "1", str(out),
    ]  # fmt: skip
    try:
        # Fixed argument list, no shell, local paths only: nothing untrusted reaches ffmpeg.
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg could not extract the frame: {exc.stderr.strip()}") from exc
    frame = Image.open(out).convert("RGBA")
    if frame.size != (FRAME_WIDTH, FRAME_HEIGHT):
        raise ValueError(f"expected a {FRAME_WIDTH}x{FRAME_HEIGHT} frame, got {frame.size}")
    return frame


def _text_font() -> ImageFont.FreeTypeFont:
    """The bold font at the supersampled text size."""
    return ImageFont.truetype(str(BOLD_FONT), round(TEXT_SHARE * DIAMETER * SUPERSAMPLE))


def _shadow_layer(size: int, centre: float, design_shadow: RGBA) -> Image.Image:
    """Blurred, offset text shadow as an RGBA layer of ``size`` x ``size`` supersampled pixels."""
    font = _text_font()
    mask = Image.new("L", (size, size), 0)
    offset = SHADOW_OFFSET_PX * SUPERSAMPLE
    ImageDraw.Draw(mask).text(
        (centre + offset, centre + offset), TEXT, font=font, fill=255, anchor="mm"
    )
    mask = mask.filter(ImageFilter.GaussianBlur(SHADOW_BLUR_PX * SUPERSAMPLE))
    alpha = mask.point(lambda value: value * design_shadow[3] // 255)
    layer = Image.new("RGBA", (size, size), (*design_shadow[:3], 0))
    layer.putalpha(alpha)
    return layer


def render_patch(design: Design) -> Image.Image:
    """The bubble of ``design`` on a transparent square patch, drawn at SUPERSAMPLE."""
    size = PATCH_PX * SUPERSAMPLE
    centre = (PAD_PX + DIAMETER / 2) * SUPERSAMPLE
    left = PAD_PX * SUPERSAMPLE
    right = (PAD_PX + DIAMETER) * SUPERSAMPLE - 1
    box = (left, left, right, right)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(box, fill=design.fill)
    draw.ellipse(box, outline=design.ring, width=round(design.ring_px * SUPERSAMPLE))
    if design.shadow is not None:
        layer = Image.alpha_composite(layer, _shadow_layer(size, centre, design.shadow))
    text_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).text(
        (centre, centre), TEXT, font=_text_font(), fill=design.text, anchor="mm"
    )
    layer = Image.alpha_composite(layer, text_layer)
    # Premultiplied resize keeps the edges of the transparent area clean.
    return (
        layer.convert("RGBa").resize((PATCH_PX, PATCH_PX), Image.Resampling.LANCZOS).convert("RGBA")
    )


def composite_at_bubble(frame: Image.Image, patch: Image.Image) -> Image.Image:
    """A copy of ``frame`` with ``patch`` alpha-composited around the bubble box."""
    out = frame.copy()
    left, top, _, _ = bubble_box()
    origin = (left - PAD_PX, top - PAD_PX)
    region = out.crop((*origin, origin[0] + PATCH_PX, origin[1] + PATCH_PX))
    out.paste(Image.alpha_composite(region, patch), origin)
    return out


def old_bubble_frame(frame: Image.Image, work: Path) -> Image.Image:
    """The frame with the current app bubble (the existing renderer) composited on it."""
    from vidgen.infrastructure.ffmpeg.label import build_label_renderer

    renderer = build_label_renderer("bubble", DEVANAGARI_FONT, BOLD_FONT)
    label_path = work / "old_label.png"
    renderer.render_label(FRAME_WIDTH, FRAME_HEIGHT, label_path)
    label = Image.open(label_path).convert("RGBA")
    return Image.alpha_composite(frame, label)


def zoom(frame: Image.Image) -> Image.Image:
    """The bottom-right crop of ``frame`` scaled by ``ZOOM`` with LANCZOS."""
    x0, y0, x1, y1 = ZOOM_BOX
    crop = frame.crop(ZOOM_BOX)
    return crop.resize(((x1 - x0) * ZOOM, (y1 - y0) * ZOOM), Image.Resampling.LANCZOS)


def stack(images: list[Image.Image]) -> Image.Image:
    """Stack images vertically with a thin gap between them."""
    width = max(image.width for image in images)
    height = sum(image.height for image in images) + SHEET_GAP_PX * (len(images) - 1)
    sheet = Image.new("RGB", (width, height), SHEET_BACKGROUND)
    top = 0
    for image in images:
        sheet.paste(image, (0, top))
        top += image.height + SHEET_GAP_PX
    return sheet


def main() -> None:
    """Write the frame, the three designs, the old-bubble zoom and the sheet."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    video = find_timing_video()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        frame = extract_frame(video, work / "frame.png")
        zooms: list[Image.Image] = [zoom(old_bubble_frame(frame, work))]
        zooms[0].save(OUT_DIR / "zoom_old.png")
        for design in DESIGNS:
            drawn = composite_at_bubble(frame, render_patch(design)).convert("RGB")
            drawn.save(OUT_DIR / f"full_{design.name}.png")
            zoomed = zoom(drawn)
            zoomed.save(OUT_DIR / f"zoom_{design.name}.png")
            zooms.append(zoomed)
    stack(zooms).save(OUT_DIR / "sheet.png")
    print(f"wrote {OUT_DIR} (source {video.name})")


if __name__ == "__main__":
    main()
