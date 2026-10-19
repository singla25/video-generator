"""Extra output-format edge cases from the test tree walk (T15): VFR input and colour tags."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.fixtures.analysis import FFMPEG, duration_of, stream
from tests.fixtures.templates import make_template
from tests.integration.ffmpeg.conftest import RenderFn
from vidgen.domain.timing import duration_within_tolerance


def make_vfr(source: Path, target: Path) -> Path:
    """Re-time frames with jitter so the file has a variable frame rate."""
    cmd = [
        FFMPEG, "-y", "-v", "error", "-i", str(source),
        "-vf", "setpts='PTS+0.012*sin(N*2.3)/TB'", "-fps_mode", "vfr",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "copy",
        str(target),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)  # noqa: S603
    return target


def test_variable_frame_rate_template_does_not_drift(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC8-E1: duration stays within 50 ms of the template for a VFR input."""
    template = make_vfr(make_template(tmp_path / "cfr.mp4"), tmp_path / "vfr.mp4")
    r = render_clip(template=template)
    assert duration_within_tolerance(
        duration_of(r.out), duration_of(template), r.plan.extension_s, tolerance_ms=50
    )


def test_colour_range_and_space_tags_are_preserved(tmp_path: Path, render_clip: RenderFn) -> None:
    """TT-AC8-E5: the output keeps the template's colour range, space, primaries and transfer."""
    source = make_template(tmp_path / "plain.mp4")
    tagged = tmp_path / "tagged.mp4"
    subprocess.run(  # noqa: S603
        [FFMPEG, "-y", "-v", "error", "-i", str(source), "-c:a", "copy", "-c:v", "libx264",
         "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-color_range", "tv",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         str(tagged)],
        check=True, capture_output=True, timeout=120,
    )  # fmt: skip
    r = render_clip(template=tagged)
    before, after = stream(tagged, "video"), stream(r.out, "video")
    for field in ("color_range", "color_space", "color_primaries", "color_transfer"):
        assert after.get(field) == before.get(field), field
