"""Shared fixtures for the FFmpeg engine tests."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.fixtures.templates import (
    PAUSE_S,
    SLOT,
    TEMPLATE_SECONDS,
    make_label_png,
    make_template,
    make_tone_wav,
)
from vidgen.domain.timing import TimingPlan, TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder

DEFAULT_METADATA = {
    "creator_entity": "Test Creator Org",
    "generated_on": "2026-10-18",
    "batch_id": "batch-0001",
}
BAND_HEIGHT = 24  # 10 % of the 240 px test frame


@dataclass(frozen=True)
class Rendered:
    """Everything a test needs to inspect one render."""

    template: Path
    out: Path
    plan: TimingPlan
    slot: tuple[float, float]
    label: Path
    metadata: Mapping[str, str]
    template_seconds: float
    new_audio: Path


@pytest.fixture
def ffmpeg_path() -> str:
    """The real ffmpeg binary (installed on the dev machine)."""
    found = shutil.which("ffmpeg")
    assert found, "ffmpeg must be installed to run the engine tests"
    return found


@pytest.fixture
def encoder(ffmpeg_path: str) -> FfmpegVideoEncoder:
    """An encoder with a generous timeout and the default 30 ms crossfade."""
    return FfmpegVideoEncoder(ffmpeg_path=ffmpeg_path, timeout_seconds=180.0, crossfade_ms=30)


@pytest.fixture(scope="session")
def shared_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Default 320x240 @ 25 fps H.264/AAC template (read-only, shared)."""
    return make_template(tmp_path_factory.mktemp("tpl") / "template.mp4")


RenderFn = Callable[..., Rendered]


@pytest.fixture
def render_clip(tmp_path: Path, encoder: FfmpegVideoEncoder, shared_template: Path) -> RenderFn:
    """Factory: build inputs, compute the plan with the domain rules, run the encoder."""
    counter = {"n": 0}

    def _render(
        *,
        new_audio_s: float = 1.0,
        amplitude: float = 0.3,
        slot: tuple[float, float] = SLOT,
        pause_s: float = PAUSE_S,
        template: Path | None = None,
        template_seconds: float = TEMPLATE_SECONDS,
        frame_width: int = 320,
        band_height: int = BAND_HEIGHT,
        metadata: Mapping[str, str] | None = None,
        new_sample_rate: int = 16000,
        new_channels: int = 1,
        cosine: bool = False,
        encoder_override: FfmpegVideoEncoder | None = None,
    ) -> Rendered:
        counter["n"] += 1
        work = tmp_path / f"case{counter['n']}"
        work.mkdir()
        tpl = template or shared_template
        new_audio = make_tone_wav(
            work / "new.wav",
            new_audio_s,
            amplitude=amplitude,
            sample_rate=new_sample_rate,
            channels=new_channels,
            cosine=cosine,
        )
        label = make_label_png(work / "label.png", frame_width, band_height)
        plan = plan_timing(slot[1] - slot[0], pause_s, new_audio_s, TimingRules())
        meta = dict(DEFAULT_METADATA if metadata is None else metadata)
        out = work / "out.mp4"
        (encoder_override or encoder).render(tpl, new_audio, slot, plan, label, meta, out)
        return Rendered(tpl, out, plan, slot, label, meta, template_seconds, new_audio)

    return _render
