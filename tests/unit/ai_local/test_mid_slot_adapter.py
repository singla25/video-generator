"""DD-39 part B: the lip-sync port takes ``start_s``; the MuseTalk adapter checks and forwards it.

The model is a stub behind a loader (the same seam the neighbouring adapter tests use); no
weights, no torch. Test tree IDs: ML-P-* and ML-N-* (see docs/test-tree/mid-slot-lipsync.md).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from tests.unit.ai_local.conftest import write_wav
from vidgen.infrastructure.fakes import FakeLipSyncer
from vidgen.infrastructure.local_ai.lipsync import MuseTalkLipSyncer


class Loader:
    """``loader(weights_dir) -> model``; records every load."""

    def __init__(self, model: Any) -> None:
        self.model = model
        self.loaded_from: list[Path] = []

    def __call__(self, weights: Path) -> Any:
        self.loaded_from.append(weights)
        return self.model


class StubMuseTalk:
    """``run(video, audio, out, start_s)``; ``start_s`` must be passed positionally."""

    def __init__(self) -> None:
        self.runs: list[tuple[Path, Path, Path, float]] = []

    def run(self, video: Path, audio: Path, out: Path, start_s: float, /) -> None:
        """Record the call and write a placeholder output."""
        self.runs.append((video, audio, out, start_s))
        out.write_bytes(b"lip-synced")


def video_file(tmp_path: Path) -> Path:
    """A placeholder input video (the stub never decodes it)."""
    path = tmp_path / "in.mp4"
    path.write_bytes(b"v")
    return path


# ---- ML-P: forwarding the start -----------------------------------------------------------


def test_default_call_passes_zero_as_the_start(weights_dir: Path, tmp_path: Path) -> None:
    """ML-P1: no start given -> the model gets 0.0 as the 4th positional argument."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), tmp_path / "out.mp4")
    assert len(model.runs) == 1
    assert model.runs[0][3] == 0.0


def test_a_start_of_two_and_a_half_seconds_reaches_the_model(
    weights_dir: Path, tmp_path: Path
) -> None:
    """ML-P2: start_s=2.5 is forwarded unchanged as the 4th positional argument."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    syncer.sync(
        video_file(tmp_path), write_wav(tmp_path / "a.wav"), tmp_path / "out.mp4", start_s=2.5
    )
    assert model.runs[0][3] == 2.5


# ---- ML-N: rejected starts ----------------------------------------------------------------


@pytest.mark.parametrize("start_s", [-1.0, -0.5, math.nan, math.inf, -math.inf])
def test_negative_or_non_finite_start_is_a_value_error_before_any_work(
    weights_dir: Path, tmp_path: Path, start_s: float
) -> None:
    """ML-N1..N3: rejected before the model loads and before any output file exists."""
    loader = Loader(StubMuseTalk())
    out = tmp_path / "out.mp4"
    syncer = MuseTalkLipSyncer(weights_dir, loader=loader)
    with pytest.raises(ValueError):
        syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), out, start_s=start_s)
    assert loader.loaded_from == []
    assert not out.exists()


# ---- FakeLipSyncer: the port stays compatible ---------------------------------------------


def test_fake_syncer_copies_the_video_when_given_a_start(tmp_path: Path) -> None:
    """ML-P3: the fake accepts the new keyword and still copies the video."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    video.write_bytes(b"\x00frames\xff" * 50)
    audio.write_bytes(b"ignored")
    FakeLipSyncer().sync(video, audio, out, start_s=2.0)
    assert out.read_bytes() == video.read_bytes()


def test_fake_syncer_old_three_argument_call_still_works(tmp_path: Path) -> None:
    """ML-P4: callers that never heard of start_s keep working."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    video.write_bytes(b"frames")
    audio.write_bytes(b"ignored")
    FakeLipSyncer().sync(video, audio, out)
    assert out.read_bytes() == b"frames"
