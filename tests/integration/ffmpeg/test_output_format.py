"""Output keeps the template's format; duration = template + extension (AC8, B10, D16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.analysis import (
    duration_of,
    fps_of,
    frame_count,
    stream,
    stream_kinds,
)
from tests.fixtures.templates import make_template
from tests.integration.ffmpeg.conftest import Rendered, RenderFn
from vidgen.domain.timing import duration_within_tolerance, expected_frame_count

AUDIO_CASES = {  # name -> new_audio_s (template slot 1.0 s, pause 0.6 s)
    "equal": 1.0,
    "shorter": 0.7,
    "stretched": 1.1,
    "absorbed": 1.3,
    "extended": 2.5,
}


def assert_same_format(template: Path, out: Path) -> None:
    """Compare every format fact the plan lists for AC8/B10."""
    tv, ov = stream(template, "video"), stream(out, "video")
    ta, oa = stream(template, "audio"), stream(out, "audio")
    assert (ov["codec_name"], ov["width"], ov["height"]) == (
        tv["codec_name"],
        tv["width"],
        tv["height"],
    )
    assert ov["pix_fmt"] == tv["pix_fmt"]
    assert fps_of(out) == pytest.approx(fps_of(template))
    assert oa["codec_name"] == ta["codec_name"]
    assert oa["sample_rate"] == ta["sample_rate"]
    assert oa["channels"] == ta["channels"]
    assert oa.get("channel_layout") == ta.get("channel_layout")
    assert stream_kinds(out).count("video") == 1
    assert stream_kinds(out).count("audio") == 1
    assert len(stream_kinds(out)) == 2


def test_h264_output_keeps_resolution_fps_codecs_and_audio_format(render_clip: RenderFn) -> None:
    """TT-AC8-P1."""
    r = render_clip()
    assert_same_format(r.template, r.out)


def test_h265_template_gives_h265_output(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC8-P2."""
    template = make_template(tmp_path / "hevc.mp4", vcodec="hevc")
    r = render_clip(template=template)
    assert stream(r.out, "video")["codec_name"] == "hevc"
    assert_same_format(r.template, r.out)


def test_mov_template_gives_mp4_output_with_same_streams(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC8-P3."""
    template = make_template(tmp_path / "t.mov", container="mov")
    r = render_clip(template=template)
    assert r.out.suffix == ".mp4"
    assert_same_format(r.template, r.out)


@pytest.mark.parametrize(("rate", "channels"), [(48000, 2), (44100, 1), (48000, 1)])
def test_audio_sample_rate_and_channel_layout_are_preserved(
    tmp_path: Path, render_clip: RenderFn, rate: int, channels: int
) -> None:
    """TT-AC8-P1, TT-AC9-E7 (B10: codec + sample rate + channel layout)."""
    template = make_template(tmp_path / "t.mp4", sample_rate=rate, channels=channels)
    r = render_clip(template=template, new_sample_rate=16000, new_channels=1)
    assert stream(r.out, "audio")["sample_rate"] == str(rate)
    assert stream(r.out, "audio")["channels"] == channels
    assert_same_format(r.template, r.out)


@pytest.mark.parametrize("case", AUDIO_CASES)
def test_duration_is_template_plus_extension_within_50_ms(render_clip: RenderFn, case: str) -> None:
    """TT-AC8-P4: equal, shorter, stretched, absorbed and extended names."""
    r = render_clip(new_audio_s=AUDIO_CASES[case])
    assert duration_within_tolerance(
        duration_of(r.out), r.template_seconds, r.plan.extension_s, tolerance_ms=50
    )
    assert (r.plan.extension_s > 0) == (case == "extended")


@pytest.mark.parametrize("case", AUDIO_CASES)
def test_video_and_audio_streams_have_the_same_length(render_clip: RenderFn, case: str) -> None:
    """TT-AC8-P4: no A/V drift after splicing."""
    r = render_clip(new_audio_s=AUDIO_CASES[case])
    video = float(stream(r.out, "video")["duration"])
    audio = float(stream(r.out, "audio")["duration"])
    expected = r.template_seconds + r.plan.extension_s
    assert video == pytest.approx(expected, abs=0.05)
    assert audio == pytest.approx(expected, abs=0.05)


@pytest.mark.parametrize("case", ["equal", "extended"])
def test_frame_count_matches_the_expected_duration(render_clip: RenderFn, case: str) -> None:
    """TT-AC8-E4: frames = round((template + extension) x fps), +/- 1."""
    r = render_clip(new_audio_s=AUDIO_CASES[case])
    expected = expected_frame_count(r.template_seconds + r.plan.extension_s, fps_of(r.out))
    assert abs(frame_count(r.out) - expected) <= 1


def test_60_fps_template_keeps_60_fps(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC8-P5 (small variant)."""
    template = make_template(tmp_path / "t60.mp4", fps=60)
    r = render_clip(template=template)
    assert fps_of(r.out) == pytest.approx(60.0)
    assert abs(frame_count(r.out) - 240) <= 1


@pytest.mark.slow
def test_full_size_1080x1300_at_60_fps_keeps_resolution_and_fps(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """TT-AC8-P5: the production format; the label band must not change the resolution."""
    template = make_template(tmp_path / "big.mp4", size=(1080, 1300), fps=60)
    r = render_clip(template=template, frame_width=1080, band_height=130)
    video = stream(r.out, "video")
    assert (video["width"], video["height"]) == (1080, 1300)
    assert fps_of(r.out) == pytest.approx(60.0)
    assert_same_format(r.template, r.out)


def test_template_file_is_not_modified(render_clip: RenderFn, shared_template: Path) -> None:
    """TT-AC8-P1: the template is read-only input."""
    before = shared_template.read_bytes()
    render_clip(new_audio_s=2.5)
    assert shared_template.read_bytes() == before


def test_output_is_a_probe_valid_mp4(render_clip: RenderFn) -> None:
    """TT-AC10-E8."""
    r: Rendered = render_clip()
    assert duration_of(r.out) > 0
