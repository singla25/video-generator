"""Bubble label composited by real ffmpeg: no extra height, bottom-right only (DD-32). LS-C-*."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.analysis import extract_frame, mean_abs_diff, pixel_mean, stream
from tests.fixtures.assets import devanagari_font, latin_font
from tests.fixtures.templates import PAUSE_S, SLOT, make_template, make_tone_wav
from vidgen.domain.timing import TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.infrastructure.ffmpeg.label import (
    PillowBubbleRenderer,
    PillowLabelRenderer,
    bubble_box,
    label_band_height,
)

METADATA = {"creator_entity": "Test Creator Org", "generated_on": "2026-10-18", "batch_id": "b-1"}
PAD = 3  # pixels around the bubble box that codec smearing may touch
SAME = 8  # mean abs diff below this = "same picture" after re-encoding


def render_with_label(
    work: Path,
    encoder: FfmpegVideoEncoder,
    template: Path,
    size: tuple[int, int],
    style: str,
    new_audio_s: float = 1.0,
) -> tuple[Path, float]:
    """Render ``template`` with the real label renderer of ``style``; return (output, extension)."""
    width, height = size
    label = work / "label.png"
    if style == "bubble":
        PillowBubbleRenderer(latin_font=latin_font()).render_label(width, height, label)
    else:
        PillowLabelRenderer(devanagari_font(), latin_font()).render_label(
            width, label_band_height(height), label
        )
    audio = make_tone_wav(work / "new.wav", new_audio_s)
    plan = plan_timing(SLOT[1] - SLOT[0], PAUSE_S, new_audio_s, TimingRules())
    out = work / "out.mp4"
    encoder.render(template, audio, SLOT, plan, label, METADATA, out)
    return out, plan.extension_s


def outside_boxes(size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Regions that must equal the template: everything above and left of the bubble."""
    width, height = size
    left, top, _, _ = bubble_box(width, height)
    return [(0, 0, width, top - PAD), (0, 0, left - PAD, height)]


def sample_times(extension: float) -> list[float]:
    """First, middle, last frames, inside the slot and after it."""
    total = 4.0 + extension
    return [0.0, 0.5, 1.5, total / 2, 3.0, total - 0.08]


@pytest.fixture
def small_template(shared_template: Path) -> Path:
    """320x240 template shared with the other ffmpeg tests."""
    return shared_template


def test_bubble_keeps_the_template_frame_size(
    tmp_path: Path, encoder: FfmpegVideoEncoder, small_template: Path
) -> None:
    """LS-C-P1."""
    out, _ = render_with_label(tmp_path, encoder, small_template, (320, 240), "bubble")
    video = stream(out, "video")
    assert (video["width"], video["height"]) == (320, 240)


def test_bubble_changes_pixels_only_in_the_bottom_right_in_every_sampled_frame(
    tmp_path: Path, encoder: FfmpegVideoEncoder, small_template: Path
) -> None:
    """LS-C-P2: the rest of the picture is the template's, frame after frame."""
    out, extension = render_with_label(tmp_path, encoder, small_template, (320, 240), "bubble")
    for index, at in enumerate(sample_times(extension)):
        frame = extract_frame(out, at, tmp_path / f"o{index}.png")
        template_frame = extract_frame(small_template, at, tmp_path / f"t{index}.png")
        assert frame.size == template_frame.size == (320, 240)
        for box in outside_boxes((320, 240)):
            assert mean_abs_diff(frame, template_frame, box) < SAME, f"changed at {at}s {box}"


def test_bubble_is_present_and_covers_the_picture_in_every_sampled_frame(
    tmp_path: Path, encoder: FfmpegVideoEncoder, small_template: Path
) -> None:
    """LS-C-P3: dark disc over the busy test picture, also on the last frames."""
    out, extension = render_with_label(tmp_path, encoder, small_template, (320, 240), "bubble")
    left, top, right, bottom = bubble_box(320, 240)
    probe = (left + max(2, (right - left) // 8), (top + bottom) // 2)
    for index, at in enumerate(sample_times(extension)):
        frame = extract_frame(out, at, tmp_path / f"o{index}.png")
        assert pixel_mean(frame, probe) < 70, f"bubble missing at {at}s"
        template_frame = extract_frame(small_template, at, tmp_path / f"t{index}.png")
        assert mean_abs_diff(frame, template_frame, (left, top, right, bottom)) > 20


def test_band_style_still_adds_the_ten_percent_band_at_the_top(
    tmp_path: Path, encoder: FfmpegVideoEncoder, small_template: Path
) -> None:
    """LS-C-P4: unchanged behaviour, size unchanged too."""
    out, _ = render_with_label(tmp_path, encoder, small_template, (320, 240), "band")
    video = stream(out, "video")
    assert (video["width"], video["height"]) == (320, 240)
    frame = extract_frame(out, 0.5, tmp_path / "o.png")
    template_frame = extract_frame(small_template, 0.5, tmp_path / "t.png")
    band = label_band_height(240)
    assert band == 24
    assert mean_abs_diff(frame, template_frame, (0, 0, 320, band)) > 40
    assert pixel_mean(frame, (2, 2)) < 70
    assert mean_abs_diff(frame, template_frame, (0, band + 4, 320, 240)) < SAME


@pytest.mark.slow
def test_bubble_on_a_production_size_frame(tmp_path: Path, encoder: FfmpegVideoEncoder) -> None:
    """LS-C-E1: 1080x1920 keeps its size; the bubble sits in the corner."""
    template = make_template(tmp_path / "big.mp4", size=(1080, 1920), seconds=4.0)
    out, _ = render_with_label(tmp_path, encoder, template, (1080, 1920), "bubble")
    video = stream(out, "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    frame = extract_frame(out, 0.5, tmp_path / "o.png")
    template_frame = extract_frame(template, 0.5, tmp_path / "t.png")
    for box in outside_boxes((1080, 1920)):
        assert mean_abs_diff(frame, template_frame, box) < SAME
    left, top, _right, bottom = bubble_box(1080, 1920)
    assert pixel_mean(frame, (left + 12, (top + bottom) // 2)) < 70
