"""Real FFmpeg output with a name gap (DD-34): the video is gap_s longer than the template.

Uses the same synthetic template and slot as the neighbouring engine tests (1.0-2.0 s name,
0.6 s pause, 4 s clip at 25 fps). The gap is applied through plan_timing(gap_s=...).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from tests.fixtures.analysis import (
    FFMPEG,
    PCM_RATE,
    decode_pcm,
    duration_of,
    fps_of,
    frame_count,
    mean_abs_diff,
    rms_dbfs,
    stream,
    window,
)
from tests.fixtures.templates import make_label_png, make_tone_wav
from vidgen.domain.timing import TimingRules, expected_frame_count, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder

SLOT = (1.0, 2.0)
PAUSE_S = 0.6
NEW_AUDIO_S = 1.0  # fills the slot exactly: no stretch, no absorbed pause, no extension
GAP_S = 0.25
METADATA = {
    "creator_entity": "Test Creator Org",
    "generated_on": "2026-10-30",
    "batch_id": "batch-0001",
}


def render_with_gap(work: Path, encoder: FfmpegVideoEncoder, template: Path, gap_s: float) -> Path:
    """Render the synthetic template with the given name gap and return the output path."""
    work.mkdir(parents=True, exist_ok=True)
    new_audio = make_tone_wav(work / "new.wav", NEW_AUDIO_S, amplitude=0.3)
    label = make_label_png(work / "label.png", 320, 24)
    plan = plan_timing(SLOT[1] - SLOT[0], PAUSE_S, NEW_AUDIO_S, TimingRules(), gap_s=gap_s)
    out = work / "out.mp4"
    encoder.render(template, new_audio, SLOT, plan, label, METADATA, out)
    return out


def rgb_frames(path: Path) -> list[Image.Image]:
    """Every video frame as an RGB image (raw decode, so the pixels are what the player sees)."""
    info = stream(path, "video")
    width, height = int(info["width"]), int(info["height"])
    raw = subprocess.run(  # noqa: S603
        [FFMPEG, "-v", "error", "-i", str(path), "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True, timeout=300,
    ).stdout  # fmt: skip
    size = width * height * 3
    return [
        Image.frombytes("RGB", (width, height), raw[i : i + size]) for i in range(0, len(raw), size)
    ]


def pixel_difference(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute pixel difference on the 0-255 scale, over the whole frame."""
    return mean_abs_diff(a, b, (0, 0, *a.size))


# ---- positive -------------------------------------------------------------------------


def test_output_is_the_template_length_plus_the_gap(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: 4.0 s template + 0.25 s gap = 4.25 s, within 50 ms."""
    out = render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S)
    expected = duration_of(shared_template) + GAP_S
    assert abs(duration_of(out) - expected) <= 0.05, (duration_of(out), expected)


def test_frame_count_is_template_frames_plus_the_gap_frames(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: round((template + gap) * fps) frames, within one frame."""
    out = render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S)
    fps = fps_of(out)
    expected = expected_frame_count(duration_of(shared_template) + GAP_S, fps)
    assert abs(frame_count(out) - expected) <= 1, (frame_count(out), expected)


def test_audio_is_as_long_as_the_video_with_the_gap(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: the padded audio region keeps audio and video the same length (60 ms)."""
    out = render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S)
    audio_s = len(decode_pcm(out)) / PCM_RATE
    assert abs(audio_s - duration_of(out)) <= 0.06, (audio_s, duration_of(out))


def test_speech_after_the_name_resumes_the_gap_later(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: the template's speech (from 2.6 s) now starts at 2.85 s, not 2.6 s.

    Output 2.3-2.8 s is the pause (silence); output 2.95-3.2 s is the speech that follows.
    """
    out = render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S)
    samples = decode_pcm(out)
    assert rms_dbfs(window(samples, 2.3, 2.8)) < -40.0
    assert rms_dbfs(window(samples, 2.95, 3.2)) > -20.0


HOLD_MAX_DIFF = 0.5  # held frames may differ by at most this (0-255 scale): codec noise only
HOLD_MOTION_RATIO = 5.0  # ...and by at most a fifth of the motion between two normal frames
CONTROL_MIN_DIFF = 5.0  # with gap 0 at least one of the same frames must differ by more than this
MOTION_MIN_DIFF = 2.0  # two consecutive moving frames must differ by at least this
MOTION_REF_FRAMES = (10, 11)  # well before the slot end, in the same output


def hold_frame_count(fps: float) -> int:
    """N = round(gap * fps) - 1 frames must be held (5 at 25 fps, one frame of slack)."""
    return round(GAP_S * fps) - 1


def test_last_slot_frame_is_held_for_the_gap(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: the slot-end frame is held for the gap, within codec tolerance.

    The clone is exact before encoding, but libx264 (CRF 18) adds small chroma noise, so the
    held frames are compared with a tolerance. The tolerance is also tied to the motion of the
    same output (testsrc2 moves every frame), so a moving picture cannot pass as a hold.
    """
    frames = rgb_frames(render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S))
    needed = hold_frame_count(fps_of(shared_template))
    start = round(SLOT[1] * fps_of(shared_template))
    motion = pixel_difference(frames[MOTION_REF_FRAMES[0]], frames[MOTION_REF_FRAMES[1]])
    assert motion >= MOTION_MIN_DIFF, f"reference motion too small to judge a hold: {motion:.2f}"
    held = frames[start]
    limit = min(HOLD_MAX_DIFF, motion / HOLD_MOTION_RATIO)
    worst = max(pixel_difference(held, frames[i]) for i in range(start, start + needed))
    assert worst <= limit, f"slot end not held: largest difference {worst:.2f} > {limit:.2f}"


def test_without_a_gap_the_slot_end_frames_do_not_hold(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 negative control: with gap 0 the same frames keep moving, so the hold check fails.

    This proves the hold test above would catch a missing hold.
    """
    frames = rgb_frames(render_with_gap(tmp_path / "nogap", encoder, shared_template, 0.0))
    needed = hold_frame_count(fps_of(shared_template))
    start = round(SLOT[1] * fps_of(shared_template))
    held = frames[start]
    worst = max(pixel_difference(held, frames[i]) for i in range(start, start + needed))
    assert worst > CONTROL_MIN_DIFF, f"gap 0 looks held (largest difference {worst:.2f})"


# ---- edge -----------------------------------------------------------------------------


def test_zero_gap_output_keeps_the_template_length(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 default: gap 0.0 gives the same length as the template, within 50 ms."""
    out = render_with_gap(tmp_path / "nogap", encoder, shared_template, 0.0)
    assert abs(duration_of(out) - duration_of(shared_template)) <= 0.05
