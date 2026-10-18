"""One end-to-end row render with the real FFmpeg engine and a fake voice (slow)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from tests.fixtures.analysis import duration_of, format_tags, fps_of, stream
from tests.fixtures.templates import make_template
from tests.integration.worker.world import FOLDER, TEMPLATE_KEY, World, build_world
from vidgen.domain.timing import duration_within_tolerance
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
from vidgen.services.render_row import RowOutcomeKind


@pytest.mark.slow
def test_real_engine_renders_a_row_that_keeps_the_template_format(
    db: Engine, tmp_path: Path
) -> None:
    """TT-AC8-P1, P4, TT-AC10-P4: output format, duration and metadata through the service."""
    template = make_template(tmp_path / "template.mp4")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    engine = FfmpegVideoEncoder(ffmpeg_path=ffmpeg, timeout_seconds=120.0, crossfade_ms=30)
    world: World = build_world(db, [("Asha Verma", "RJ/12/097")], encoder=engine)
    world.storage.files[TEMPLATE_KEY] = template.read_bytes()
    world.voice.seconds = 0.9  # 0.6 s slot, 0.6 s pause: stretch, no extension
    outcome = world.renderer.render(world.batch_id, world.rows[2])
    assert outcome.kind is RowOutcomeKind.COMPLETED
    key = f"{FOLDER}/RJ_12_097.mp4"
    out = tmp_path / "out.mp4"
    out.write_bytes(world.storage.files[key])
    assert (stream(out, "video")["width"], stream(out, "video")["height"]) == (320, 240)
    assert fps_of(out) == fps_of(template)
    assert stream(out, "audio")["sample_rate"] == stream(template, "audio")["sample_rate"]
    assert duration_within_tolerance(duration_of(out), 4.0, 0.0, tolerance_ms=50)
    tags = format_tags(out)
    assert tags["batch_id"] == str(world.batch_id)
    assert tags["generated_on"] == datetime(2026, 10, 18, tzinfo=UTC).date().isoformat()
    assert "Asha" not in " ".join(tags.values())
