"""Label band overlay on every frame (AC10, D-10). Uses a synthetic PNG, no font needed."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.analysis import extract_frame, mean_abs_diff, pixel_mean, stream
from tests.fixtures.templates import make_template
from tests.integration.ffmpeg.conftest import BAND_HEIGHT, RenderFn

WIDTH = 320
BAND_BOX = (0, 0, WIDTH, BAND_HEIGHT)
BELOW_BOX = (0, BAND_HEIGHT + 4, WIDTH, 240)


def band_matches_label(frame: Image.Image, label: Path) -> float:
    """Mean absolute difference between the frame's top band and the label image."""
    return mean_abs_diff(frame, Image.open(label).convert("RGB"), BAND_BOX)


def sample_times(duration: float) -> list[float]:
    """First, middle, last and a few more frame times."""
    step = 1 / 25
    return [0.0, 0.5, 1.5, duration / 2, duration - 2 * step, duration - step * 1.5]


def test_band_is_present_in_first_middle_and_last_frames(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC10-P1, P2: the label is burned into the top band of sampled frames."""
    r = render_clip()
    for index, at in enumerate(sample_times(4.0)):
        frame = extract_frame(r.out, at, tmp_path / f"f{index}.png")
        assert band_matches_label(frame, r.label) < 14, f"band missing at {at}s"


def test_band_covers_the_full_width(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC10-P1 (D-10): left edge, right edge and centre of the band row all match."""
    r = render_clip()
    frame = extract_frame(r.out, 1.0, tmp_path / "f.png")
    label = Image.open(r.label).convert("RGB")
    for box in [(0, 0, 8, BAND_HEIGHT), (WIDTH - 8, 0, WIDTH, BAND_HEIGHT), (150, 0, 170, 20)]:
        assert mean_abs_diff(frame, label, box) < 20


def test_band_is_opaque_and_hides_the_picture_underneath(
    tmp_path: Path, render_clip: RenderFn, shared_template: Path
) -> None:
    """TT-AC10-P1 (D-10): the template top area is covered, not blended."""
    r = render_clip()
    out_frame = extract_frame(r.out, 0.5, tmp_path / "o.png")
    template_frame = extract_frame(shared_template, 0.5, tmp_path / "t.png")
    assert mean_abs_diff(out_frame, template_frame, BAND_BOX) > 40  # covered
    # dark background pixel of the band (corner) stays dark: no see-through
    assert pixel_mean(out_frame, (2, 2)) < 70


def test_picture_below_the_band_is_unchanged(
    tmp_path: Path, render_clip: RenderFn, shared_template: Path
) -> None:
    """TT-AC10-P1, TT-AC8-P1: resolution unchanged, the rest of the frame is not scaled."""
    r = render_clip()
    for at in (0.2, 3.5):  # outside the slot, no timing shift without extension
        out_frame = extract_frame(r.out, at, tmp_path / "o.png")
        template_frame = extract_frame(shared_template, at, tmp_path / "t.png")
        assert out_frame.size == template_frame.size == (WIDTH, 240)
        assert mean_abs_diff(out_frame, template_frame, BELOW_BOX) < 8


def test_label_is_still_on_every_sampled_frame_after_an_extension(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC10-E7: also inside the extended region and on the final frames."""
    r = render_clip(new_audio_s=2.5)
    total = 4.0 + r.plan.extension_s
    inside_extension = 2.0 + r.plan.extension_s / 2
    for index, at in enumerate([inside_extension, total / 2, total - 0.08, total - 0.05]):
        frame = extract_frame(r.out, at, tmp_path / f"e{index}.png")
        assert band_matches_label(frame, r.label) < 14, f"band missing at {at}s"


@pytest.mark.parametrize("size", [(240, 320), (480, 270)])
def test_label_works_on_portrait_and_landscape_frames(
    tmp_path: Path, render_clip: RenderFn, size: tuple[int, int]
) -> None:
    """TT-AC10-E1."""
    width, height = size
    template = make_template(tmp_path / "t.mp4", size=size)
    band = height // 10 + 1
    r = render_clip(template=template, frame_width=width, band_height=band)
    video = stream(r.out, "video")
    assert (video["width"], video["height"]) == size
    frame = extract_frame(r.out, 0.5, tmp_path / "f.png")
    label = Image.open(r.label).convert("RGB")
    assert mean_abs_diff(frame, label, (0, 0, width, band)) < 14


def test_band_on_bright_and_dark_pictures_keeps_contrast(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC10-E3: light text bar vs dark band is preserved whatever lies underneath."""
    r = render_clip()
    frame = extract_frame(r.out, 1.0, tmp_path / "f.png")
    bar = pixel_mean(frame, (WIDTH // 2, BAND_HEIGHT // 2))
    background = pixel_mean(frame, (4, 2))
    assert bar - background > 120
