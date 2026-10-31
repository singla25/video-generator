"""DD-40: two name slots through the real FFmpeg engine (slow; fakes for the AI parts).

The output is as long as the template plus the extension and the name gap of BOTH slots, keeps
the frame size, the frame rate and the audio, and carries the bubble label. The bubble is a
single overlay: a region check cannot count overlays, so "drawn once" is asserted by the fake
encoder tests (MS-P6, MS-P7) instead. Test tree IDs: MS-V-* in
docs/test-tree/multi-slot-pipeline.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine

from tests.fixtures.analysis import duration_of, extract_frame, fps_of, mean_abs_diff, stream
from tests.fixtures.assets import latin_font
from tests.fixtures.templates import make_template
from tests.integration.worker.test_render_row_multi_slot import multi_slot_renderer
from tests.integration.worker.world import (
    CREATOR,
    FOLDER,
    PAUSE_S,
    TEMPLATE_KEY,
    World,
    build_world,
)
from vidgen.domain.timing import TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.infrastructure.ffmpeg.label import PillowBubbleRenderer, bubble_box
from vidgen.services.render_row import RenderConfig, RowOutcomeKind

FIRST = (1.0, 2.0)  # the template's own slot
EXTRA = ((3.0, 3.5),)  # a second slot, 0.5 s long
VOICE_S = 2.0  # long enough that both slots extend the video
GAP_S = 0.25  # name gap after every name (DD-34)
PRESENT = 8  # mean abs diff inside the bubble box at or above this = the bubble is drawn


@pytest.mark.slow
@pytest.mark.parametrize("fps", [25, 60])
def test_two_slots_give_the_template_length_plus_both_extensions_and_gaps(
    db: Engine, tmp_path: Path, fps: int
) -> None:
    """MS-V-P1: duration within 0.15 s, size, frame rate, audio and the bubble, at 25 and 60 fps."""
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    template = make_template(tmp_path / "template.mp4", fps=fps)
    engine = FfmpegVideoEncoder(ffmpeg_path=ffmpeg, timeout_seconds=120.0, crossfade_ms=30)
    config = RenderConfig(creator_entity=CREATOR, pause_s=PAUSE_S, name_gap_s=GAP_S)
    world: World = build_world(
        db, [("Asha Verma", "RJ/12/097")], slot=FIRST, config=config, encoder=engine
    )
    world.storage.files[TEMPLATE_KEY] = template.read_bytes()
    world.voice.seconds = VOICE_S
    renderer = multi_slot_renderer(
        world,
        EXTRA,
        config=config,
        labels=PillowBubbleRenderer(latin_font=latin_font()),
    )
    outcome = renderer.render(world.batch_id, world.rows[2])
    assert outcome.kind is RowOutcomeKind.COMPLETED

    expected_delta = sum(
        plan_timing(
            round(end - start, 6), PAUSE_S, VOICE_S, TimingRules(), gap_s=GAP_S
        ).duration_delta_s
        for start, end in (FIRST, *EXTRA)
    )
    out = tmp_path / "out.mp4"
    out.write_bytes(world.storage.files[f"{FOLDER}/RJ_12_097.mp4"])
    assert abs(duration_of(out) - (duration_of(template) + expected_delta)) <= 0.15
    video = stream(out, "video")
    assert (video["width"], video["height"]) == (320, 240)
    assert fps_of(out) == fps_of(template)
    assert stream(out, "audio")["sample_rate"] == stream(template, "audio")["sample_rate"]

    frame = extract_frame(out, 0.5, tmp_path / "o.png")
    template_frame = extract_frame(template, 0.5, tmp_path / "t.png")
    assert mean_abs_diff(frame, template_frame, bubble_box(320, 240)) >= PRESENT
