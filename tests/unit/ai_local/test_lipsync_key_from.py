"""DD-40: the lip-sync port takes ``key_from``; the MuseTalk adapter forwards it to the model.

The model is a stub behind the same loader seam the neighbouring adapter tests use. The stub
takes exactly five positional arguments (video, audio, out, start_s, key_from), so a call that
does not pass the key source fails. Test tree IDs: MS-K-* in docs/test-tree/multi-slot-pipeline.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    """``run(video, audio, out, start_s, key_from)``; all five are passed positionally."""

    def __init__(self) -> None:
        self.runs: list[tuple[Path, Path, Path, float, Path | None]] = []

    def run(
        self,
        video: Path,
        audio: Path,
        out: Path,
        start_s: float,
        key_from: Path | None,
        /,
    ) -> None:
        """Record the call and write a placeholder output."""
        self.runs.append((video, audio, out, start_s, key_from))
        out.write_bytes(b"lip-synced")


def video_file(tmp_path: Path) -> Path:
    """A placeholder input video (the stub never decodes it)."""
    path = tmp_path / "in.mp4"
    path.write_bytes(b"v")
    return path


# ---- MS-K-P: forwarding -------------------------------------------------------------------


def test_the_adapter_passes_the_key_source_as_the_fifth_argument(
    weights_dir: Path, tmp_path: Path
) -> None:
    """MS-K-P1: key_from reaches the model unchanged, after the start."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    template = video_file(tmp_path)
    syncer.sync(
        template,
        write_wav(tmp_path / "a.wav"),
        tmp_path / "out.mp4",
        start_s=2.5,
        key_from=template,
    )
    assert len(model.runs) == 1
    assert model.runs[0][3] == 2.5
    assert model.runs[0][4] == template


def test_a_key_source_that_is_not_the_input_is_forwarded_as_given(
    weights_dir: Path, tmp_path: Path
) -> None:
    """MS-K-P2: the key source is not replaced by the input video."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    key = tmp_path / "template.mp4"
    key.write_bytes(b"t")
    syncer.sync(
        video_file(tmp_path),
        write_wav(tmp_path / "a.wav"),
        tmp_path / "out.mp4",
        start_s=4.0,
        key_from=key,
    )
    assert model.runs[0][4] == key


def test_defaults_pass_zero_as_the_start_and_none_as_the_key_source(
    weights_dir: Path, tmp_path: Path
) -> None:
    """MS-K-P3: a call without the new keywords behaves as before (0.0 and None)."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    syncer.sync(video_file(tmp_path), write_wav(tmp_path / "a.wav"), tmp_path / "out.mp4")
    assert model.runs[0][3] == 0.0
    assert model.runs[0][4] is None


def test_an_explicit_none_key_source_is_passed_as_none(weights_dir: Path, tmp_path: Path) -> None:
    """MS-K-P4: key_from=None (the first pass of a row) reaches the model as None."""
    model = StubMuseTalk()
    syncer = MuseTalkLipSyncer(weights_dir, loader=Loader(model))
    syncer.sync(
        video_file(tmp_path),
        write_wav(tmp_path / "a.wav"),
        tmp_path / "out.mp4",
        start_s=10.0,
        key_from=None,
    )
    assert model.runs[0][3] == 10.0
    assert model.runs[0][4] is None


# ---- FakeLipSyncer: accepts both keywords -------------------------------------------------


def test_fake_syncer_accepts_a_key_source_and_copies_the_video(tmp_path: Path) -> None:
    """MS-K-P5: the fake ignores the key source and copies the video."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    video.write_bytes(b"\x00frames\xff" * 50)
    audio.write_bytes(b"ignored")
    FakeLipSyncer().sync(video, audio, out, start_s=2.0, key_from=video)
    assert out.read_bytes() == video.read_bytes()


def test_fake_syncer_accepts_the_key_source_as_none(tmp_path: Path) -> None:
    """MS-K-P6: key_from=None is accepted by the fake."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    video.write_bytes(b"frames")
    audio.write_bytes(b"ignored")
    FakeLipSyncer().sync(video, audio, out, start_s=0.0, key_from=None)
    assert out.read_bytes() == b"frames"
