"""MuseTalk lip-syncer contract (M2 plan AC5, risk R1). The model is a stub; ffmpeg is real."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.analysis import duration_of, fps_of, frame_count
from tests.fixtures.media import FFMPEG, make_video
from tests.unit.infra.ai.support import Blocker, Factory, leftovers, write_wav
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ai.errors import AdapterTimeoutError, ModelLoadError
from vidgen.infrastructure.ai.musetalk_lipsyncer import MuseTalkLipSyncer
from vidgen.ports import LipSyncer

MODEL_FPS = 25
SIZE = (64, 64)


class StubMuseTalk:
    """``run(video, audio, out)``: records the input fps, writes a 25 fps video."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        blocker: Blocker | None = None,
        write_garbage: bool = False,
    ) -> None:
        self.error, self.blocker, self.write_garbage = error, blocker, write_garbage
        self.seen_fps: list[float] = []

    def run(self, video: Path, audio: Path, out: Path) -> None:
        self.seen_fps.append(fps_of(video))
        if self.blocker:
            self.blocker.wait()
        if self.error:
            out.write_bytes(b"partial")  # a crashing model may leave a half-written file
            raise self.error
        if self.write_garbage:
            out.write_bytes(b"not a video")
            return
        subprocess.run(  # noqa: S603
            [FFMPEG, "-y", "-v", "error", "-i", str(video), "-r", str(MODEL_FPS), str(out)],
            check=True,
            capture_output=True,
            timeout=60,
        )


@pytest.fixture
def template(tmp_path: Path) -> Path:
    return make_video(tmp_path / "template.mp4", seconds=1.0, size=SIZE, fps=60)


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "new.wav", 1.0)


def make(engine: StubMuseTalk, **kwargs: Any) -> tuple[MuseTalkLipSyncer, Factory]:
    factory = Factory(engine)
    return MuseTalkLipSyncer(engine_factory=factory, **kwargs), factory


def test_lipsync_output_is_back_at_the_template_frame_rate(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-P1: model runs at 25 fps; the written video is 60 fps again, same duration."""
    engine = StubMuseTalk()
    syncer, _ = make(engine)
    out = tmp_path / "out.mp4"
    syncer.sync(template, audio, out)
    assert engine.seen_fps == [pytest.approx(MODEL_FPS)]
    assert fps_of(out) == pytest.approx(60)
    assert duration_of(out) == pytest.approx(duration_of(template), abs=0.1)
    assert frame_count(out) == pytest.approx(frame_count(template), abs=2)


@pytest.mark.parametrize("fps", [24, 25, 30])
def test_lipsync_restores_other_template_frame_rates(tmp_path: Path, audio: Path, fps: int) -> None:
    """M2-S4-P2 / E1: 25 fps template needs no resample; 24 and 30 are restored."""
    template = make_video(tmp_path / "t.mp4", seconds=1.0, size=SIZE, fps=fps)
    out = tmp_path / "out.mp4"
    make(StubMuseTalk())[0].sync(template, audio, out)
    assert fps_of(out) == pytest.approx(fps)


def test_lipsync_satisfies_the_lip_syncer_port(tmp_path: Path, template: Path, audio: Path) -> None:
    """M2-S4-P3."""
    syncer: LipSyncer = make(StubMuseTalk())[0]
    syncer.sync(template, audio, tmp_path / "o.mp4")
    assert (tmp_path / "o.mp4").exists()


def test_lipsync_loads_the_model_lazily_and_once(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-P4 (D-M2-3)."""
    syncer, factory = make(StubMuseTalk())
    assert factory.calls == 0
    syncer.sync(template, audio, tmp_path / "1.mp4")
    syncer.sync(template, audio, tmp_path / "2.mp4")
    assert factory.calls == 1


def test_lipsync_leaves_no_intermediate_files_on_success(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-E2: the 25 fps working copy is cleaned up."""
    make(StubMuseTalk())[0].sync(template, audio, tmp_path / "out.mp4")
    assert leftovers(tmp_path, {"template.mp4", "new.wav", "out.mp4"}) == set()


def test_lipsync_missing_video_fails_without_output(tmp_path: Path, audio: Path) -> None:
    """M2-S4-N1."""
    syncer, factory = make(StubMuseTalk())
    with pytest.raises(FileNotFoundError):
        syncer.sync(tmp_path / "nope.mp4", audio, tmp_path / "o.mp4")
    assert factory.calls == 0
    assert not (tmp_path / "o.mp4").exists()


def test_lipsync_missing_audio_fails_without_output(tmp_path: Path, template: Path) -> None:
    """M2-S4-N2."""
    with pytest.raises(FileNotFoundError):
        make(StubMuseTalk())[0].sync(template, tmp_path / "nope.wav", tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_lipsync_empty_audio_is_rejected_and_writes_nothing(tmp_path: Path, template: Path) -> None:
    """M2-S4-E3: zero-length audio -> LIPSYNC_LOW_QUALITY (nothing to sync), model not called."""
    engine = StubMuseTalk()
    with pytest.raises(DomainError) as info:
        make(engine)[0].sync(template, write_wav(tmp_path / "z.wav", 0), tmp_path / "o.mp4")
    assert info.value.code is FailureCode.LIPSYNC_LOW_QUALITY
    assert engine.seen_fps == []
    assert not (tmp_path / "o.mp4").exists()


def test_lipsync_corrupt_video_is_a_coded_error_without_output(tmp_path: Path, audio: Path) -> None:
    """M2-S4-N3: a file that is not a video -> CORRUPT_VIDEO."""
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a video" * 10)
    with pytest.raises(DomainError) as info:
        make(StubMuseTalk())[0].sync(bad, audio, tmp_path / "o.mp4")
    assert info.value.code is FailureCode.CORRUPT_VIDEO
    assert not (tmp_path / "o.mp4").exists()


def test_lipsync_model_crash_leaves_no_partial_output(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-N4: crash mid-render -> LIPSYNC_LOW_QUALITY error, nothing left behind."""
    with pytest.raises(DomainError) as info:
        make(StubMuseTalk(error=RuntimeError("mps oom")))[0].sync(
            template, audio, tmp_path / "o.mp4"
        )
    assert info.value.code is FailureCode.LIPSYNC_LOW_QUALITY
    assert leftovers(tmp_path, {"template.mp4", "new.wav"}) == set()


def test_lipsync_unreadable_model_output_is_an_error_without_output(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-N5: the model wrote garbage; resampling fails; out is not created."""
    with pytest.raises(DomainError):
        make(StubMuseTalk(write_garbage=True))[0].sync(template, audio, tmp_path / "o.mp4")
    assert leftovers(tmp_path, {"template.mp4", "new.wav"}) == set()


def test_lipsync_model_load_failure_is_a_model_load_error(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-N6."""
    syncer = MuseTalkLipSyncer(engine_factory=Factory(error=OSError("no weights")))
    with pytest.raises(ModelLoadError):
        syncer.sync(template, audio, tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_lipsync_retry_after_a_crash_succeeds(tmp_path: Path, template: Path, audio: Path) -> None:
    """M2-S4-E4: retry safety. The same adapter works after a failed attempt."""
    out = tmp_path / "o.mp4"
    syncer, _ = make(StubMuseTalk(error=RuntimeError("once")))
    with pytest.raises(DomainError):
        syncer.sync(template, audio, out)
    syncer2, _ = make(StubMuseTalk())
    syncer2.sync(template, audio, out)
    assert fps_of(out) == pytest.approx(60)


def test_lipsync_timeout_raises_and_leaves_no_output(
    tmp_path: Path, template: Path, audio: Path
) -> None:
    """M2-S4-E5."""
    blocker = Blocker()
    syncer, _ = make(StubMuseTalk(blocker=blocker), timeout_s=0.2)
    try:
        with pytest.raises(AdapterTimeoutError) as info:
            syncer.sync(template, audio, tmp_path / "o.mp4")
        assert info.value.code is FailureCode.RENDER_TIMEOUT
    finally:
        blocker.release.set()
    assert not (tmp_path / "o.mp4").exists()
