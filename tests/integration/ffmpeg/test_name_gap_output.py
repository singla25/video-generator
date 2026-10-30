"""Real FFmpeg output with a name gap (DD-34): the video is gap_s longer than the template.

Uses the same synthetic template and slot as the neighbouring engine tests (1.0-2.0 s name,
0.6 s pause, 4 s clip at 25 fps). The gap is applied through plan_timing(gap_s=...).
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.analysis import (
    PCM_RATE,
    decode_pcm,
    duration_of,
    fps_of,
    frame_count,
    frame_hashes,
    rms_dbfs,
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


def test_last_slot_frame_is_held_for_the_gap(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 positive: the frame at the slot end is held (identical frames) for the gap.

    N = round(gap * fps) - 1 (5 at 25 fps). The hold ends where the picture moves again.
    shared_template is testsrc2, which moves every frame, so the motion check below is active.
    """
    out = render_with_gap(tmp_path / "gap", encoder, shared_template, GAP_S)
    fps = fps_of(shared_template)
    needed = round(GAP_S * fps) - 1
    slot_end_frame = round(SLOT[1] * fps)
    hashes = frame_hashes(out)
    held = hashes[slot_end_frame]
    hold_end = slot_end_frame
    while hold_end < len(hashes) and hashes[hold_end] == held:
        hold_end += 1
    assert hold_end - slot_end_frame >= needed, (hold_end - slot_end_frame, needed)
    assert hold_end < len(hashes), "the picture never moves again after the slot"
    assert len(set(hashes[hold_end : hold_end + needed])) > 1, "no motion after the hold"


# ---- edge -----------------------------------------------------------------------------


def test_zero_gap_output_keeps_the_template_length(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path
) -> None:
    """DD-34 default: gap 0.0 gives the same length as the template, within 50 ms."""
    out = render_with_gap(tmp_path / "nogap", encoder, shared_template, 0.0)
    assert abs(duration_of(out) - duration_of(shared_template)) <= 0.05
