"""Audio splice: only the slot changes (AC9, A9, B10, D16, D-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.analysis import (
    PCM_RATE,
    active_end,
    decode_pcm,
    diff_dbfs,
    frame_hashes,
    longest_run,
    loudness_lufs,
    max_step,
    rms_dbfs,
    window,
    window_n,
)
from tests.fixtures.templates import make_label_png, make_template, make_tone_wav
from tests.integration.ffmpeg.conftest import Rendered, RenderFn
from vidgen.domain.timing import TimingPlan, TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder

CROSSFADE_S = 0.030
GUARD_S = CROSSFADE_S + 0.06  # crossfade zone + codec priming guard
MAX_DIFF_DB = -40.0  # A9
CASES = {"equal": 1.0, "shorter": 0.7, "stretched": 1.1, "absorbed": 1.3, "extended": 2.5}


def outside_slot_diffs(r: Rendered) -> list[float]:
    """Level (dBFS) of output minus template where the template is untouched.

    Head: before the slot. Tail: after the spoken part; the template tail is shifted in the
    output by the extension, and starts after the part of the pause that was absorbed.
    """
    template, out = decode_pcm(r.template), decode_pcm(r.out)
    start, end = r.slot
    diffs: list[float] = []
    head_end = start - GUARD_S
    if head_end > 0.15:
        diffs.append(diff_dbfs(window(template, 0.05, head_end), window(out, 0.05, head_end)))
    tail_t = end + r.plan.pause_absorbed_s + GUARD_S
    tail_o = tail_t + r.plan.extension_s
    tail_end_t = r.template_seconds - 0.1
    if tail_end_t - tail_t > 0.15:
        count = round((tail_end_t - tail_t) * PCM_RATE)
        diffs.append(diff_dbfs(window_n(template, tail_t, count), window_n(out, tail_o, count)))
    return diffs


# ---- positive -------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_audio_outside_the_slot_matches_the_template(render_clip: RenderFn, case: str) -> None:
    """TT-AC9-P7, P2-P5 (A9): difference <= -40 dB RMS outside slot minus crossfade zones."""
    r = render_clip(new_audio_s=CASES[case])
    diffs = outside_slot_diffs(r)
    assert len(diffs) == 2
    assert all(d <= MAX_DIFF_DB for d in diffs), diffs


def test_spoken_part_contains_the_new_audio_not_the_old_name(render_clip: RenderFn) -> None:
    """TT-AC9-P1: the slot is audible and replaced (new tone differs from the 880 Hz template)."""
    r = render_clip(new_audio_s=1.0, amplitude=0.3)
    template, out = decode_pcm(r.template), decode_pcm(r.out)
    inner_t, inner_o = window(template, 1.1, 1.9), window(out, 1.1, 1.9)
    assert rms_dbfs(inner_o) > -30.0  # not silent
    assert diff_dbfs(inner_t, inner_o) > -20.0  # but different from the old name


@pytest.mark.parametrize("amplitude", [0.05, 0.9])
@pytest.mark.parametrize("case", ["equal", "absorbed"])
def test_slot_loudness_is_within_one_lu_of_the_template(
    render_clip: RenderFn, case: str, amplitude: float
) -> None:
    """TT-AC9-P9 (B10, ITU-R BS.1770): quiet or loud TTS output is normalised to the template."""
    r = render_clip(new_audio_s=CASES[case], amplitude=amplitude)
    expected = loudness_lufs(r.template, 1.1, 1.9)
    actual = loudness_lufs(r.out, 1.1, 1.9)
    assert abs(actual - expected) <= 1.0


def test_crossfade_removes_clicks_at_both_slot_edges(render_clip: RenderFn) -> None:
    """TT-AC9-P8: a cosine tone starts and ends at full level; a hard cut would jump ~0.3."""
    r = render_clip(new_audio_s=1.0, cosine=True)
    out = decode_pcm(r.out)
    start, end = r.slot
    assert max_step(window(out, start - 0.05, start + 0.05)) < 0.2
    assert max_step(window(out, end - 0.05, end + 0.05)) < 0.2


@pytest.mark.parametrize("case", ["equal", "shorter", "stretched", "absorbed"])
def test_spoken_part_ends_where_the_plan_says_within_the_crossfade(
    render_clip: RenderFn, case: str
) -> None:
    """TT-AC9-P2, P8: the name is stretched/padded to plan.final_audio_s (+/- crossfade + 20 ms)."""
    r = render_clip(new_audio_s=CASES[case])
    out = decode_pcm(r.out)
    start = r.slot[0]
    end = active_end(out, start + 0.3, start + 2.0)
    expected = start + r.plan.final_audio_s
    assert end == pytest.approx(expected, abs=CROSSFADE_S + 0.02)


def test_stretch_really_shortens_the_name_instead_of_letting_it_run_long(
    render_clip: RenderFn,
) -> None:
    """TT-AC9-P2, P3: without the stretch the 1.3 s name would end at 2.3 s."""
    r = render_clip(new_audio_s=1.3)
    out = decode_pcm(r.out)
    end = active_end(out, 1.3, 3.0)
    assert end < 1.0 + 1.3 - 0.1


@pytest.mark.parametrize("case", ["equal", "shorter", "absorbed"])
def test_spoken_part_starts_at_the_slot_start_within_the_crossfade(
    render_clip: RenderFn, case: str
) -> None:
    """TT-AC9-P8: the template's own speech stops and the new name is audible at the slot start."""
    r = render_clip(new_audio_s=CASES[case], cosine=True)
    out = decode_pcm(r.out)
    start = r.slot[0]
    assert rms_dbfs(window(out, start + CROSSFADE_S + 0.02, start + 0.25)) > -20.0


def test_shorter_name_keeps_the_following_speech_at_the_same_time(render_clip: RenderFn) -> None:
    """TT-AC9-P5: the pause is padded, nothing after the slot moves."""
    r = render_clip(new_audio_s=0.7)
    assert r.plan.pause_padding_s == pytest.approx(0.3)
    out = decode_pcm(r.out)
    padded = window(out, 1.7 + 0.05, 2.0 - 0.05)  # between the short name and the old slot end
    assert rms_dbfs(padded) < -40.0  # silence, not leftover template speech
    assert rms_dbfs(window(out, 2.7, 3.5)) > -20.0  # speech resumes where the template does


def test_extension_retimes_slot_frames_slower_without_freezing(render_clip: RenderFn) -> None:
    """TT-AC9-P4, D-11: the video grows; frames under the slot are slowed, not frozen."""
    r = render_clip(new_audio_s=2.5)
    assert r.plan.extension_s > 0.3
    hashes = frame_hashes(r.out, skip_top=24)
    slowdown = (1.0 + r.plan.extension_s) / 1.0
    assert longest_run(hashes) <= int(slowdown * 2) + 1  # stretched frames, no long freeze
    start, end = r.slot
    fps = 25
    inside = hashes[int(start * fps) : int((end + r.plan.extension_s) * fps)]
    assert len(set(inside)) >= len(inside) // 3  # still moving
    # frames before the slot are untouched in timing: same count of distinct frames as template
    template_hashes = frame_hashes(r.template, skip_top=24)
    assert len(hashes) == pytest.approx(len(template_hashes) + r.plan.extension_s * fps, abs=2)


# ---- negative -------------------------------------------------------------------------


@pytest.mark.parametrize("factor", [0.7, 0.84, 1.2])
def test_a_plan_stretching_more_than_15_percent_is_refused(
    tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path, factor: float
) -> None:
    """TT-AC9-N4 / A9 / R3.5: the engine never executes a stretch beyond +/-15 %."""
    bad = TimingPlan(
        stretch_factor=factor,
        pause_absorbed_s=0.0,
        extension_s=0.0,
        pause_padding_s=0.0,
        final_audio_s=1.0,
    )
    new = make_tone_wav(tmp_path / "n.wav", 1.0)
    label = make_label_png(tmp_path / "l.png", 320, 24)
    out = tmp_path / "out.mp4"
    with pytest.raises(ValueError, match="stretch"):
        encoder.render(shared_template, new, (1.0, 2.0), bad, label, {}, out)
    assert not out.exists()


@pytest.mark.parametrize("ms", [19, 51, 0, 500])
def test_crossfade_outside_20_to_50_ms_is_rejected_at_construction(
    ffmpeg_path: str, ms: int
) -> None:
    """TT-AC9-N4."""
    with pytest.raises(ValueError, match="crossfade"):
        FfmpegVideoEncoder(ffmpeg_path=ffmpeg_path, timeout_seconds=10.0, crossfade_ms=ms)


@pytest.mark.parametrize("ms", [20, 35, 50])
def test_crossfade_inside_20_to_50_ms_is_accepted(ffmpeg_path: str, ms: int) -> None:
    """TT-AC9-P8."""
    FfmpegVideoEncoder(ffmpeg_path=ffmpeg_path, timeout_seconds=10.0, crossfade_ms=ms)


# ---- edge -----------------------------------------------------------------------------


def test_slot_at_the_very_start_of_the_template(render_clip: RenderFn) -> None:
    """TT-AC9-E5: no audio before the slot, so no head crossfade."""
    r = render_clip(new_audio_s=0.9, slot=(0.0, 1.0), pause_s=0.5)
    diffs = outside_slot_diffs(r)
    assert diffs and all(d <= MAX_DIFF_DB for d in diffs)


def test_slot_at_the_very_end_of_the_template(render_clip: RenderFn) -> None:
    """TT-AC9-E5: slot ends 0.1 s before the end; no room for a tail crossfade."""
    r = render_clip(new_audio_s=0.8, slot=(3.0, 3.9), pause_s=0.1)
    diffs = outside_slot_diffs(r)
    assert diffs and all(d <= MAX_DIFF_DB for d in diffs)


def test_zero_length_pause_with_stretch_and_extension(render_clip: RenderFn) -> None:
    """TT-AC9-E4: the pause cannot absorb anything, so the video grows."""
    r = render_clip(new_audio_s=1.6, slot=(3.0, 3.9), pause_s=0.0)
    assert r.plan.pause_absorbed_s == 0
    assert r.plan.extension_s > 0
    assert all(d <= MAX_DIFF_DB for d in outside_slot_diffs(r))


def test_stereo_48k_template_splices_cleanly(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC9-E7."""
    template = make_template(tmp_path / "st.mp4", sample_rate=48000, channels=2)
    r = render_clip(template=template, new_audio_s=1.3, new_sample_rate=48000, new_channels=2)
    assert all(d <= MAX_DIFF_DB for d in outside_slot_diffs(r))


def test_44k_mono_template_splices_cleanly(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC9-E7."""
    template = make_template(tmp_path / "m44.mp4", sample_rate=44100, channels=1)
    r = render_clip(template=template, new_audio_s=1.3, new_sample_rate=22050)
    assert all(d <= MAX_DIFF_DB for d in outside_slot_diffs(r))


def test_plan_matches_domain_planning(render_clip: RenderFn) -> None:
    """Contract check: the engine is fed by the domain planner (not re-tested here)."""
    r = render_clip(new_audio_s=1.3)
    assert r.plan == plan_timing(1.0, 0.6, 1.3, TimingRules())
