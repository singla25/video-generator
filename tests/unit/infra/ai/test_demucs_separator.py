"""Demucs vocal separator and the new VocalSeparator port (M2 plan D-M2-1, AC4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.unit.infra.ai.support import Blocker, Factory, leftovers, read_wav_info, write_wav
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ai.demucs_separator import DemucsSeparator
from vidgen.infrastructure.ai.errors import AdapterTimeoutError, ModelLoadError
from vidgen.infrastructure.fakes import FakeVocalSeparator
from vidgen.ports import VocalSeparator

RATE = 44100


class StubDemucs:
    """``separate(audio) -> (vocals, accompaniment, sample_rate)`` with float mono samples."""

    def __init__(
        self, count: int = RATE, *, error: Exception | None = None, blocker: Blocker | None = None
    ) -> None:
        self.count, self.error, self.blocker = count, error, blocker
        self.calls: list[Path] = []

    def separate(self, audio: Path) -> tuple[list[float], list[float], int]:
        self.calls.append(audio)
        if self.blocker:
            self.blocker.wait()
        if self.error:
            raise self.error
        return [0.3] * self.count, [0.1] * self.count, RATE


def make(engine: StubDemucs, **kwargs: Any) -> tuple[DemucsSeparator, Factory]:
    factory = Factory(engine)
    return DemucsSeparator(engine_factory=factory, **kwargs), factory


@pytest.fixture
def song(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "song.wav", 2, RATE)


# ---- port and fake --------------------------------------------------------------------


def test_vocal_separator_port_is_exported_from_ports(tmp_path: Path, song: Path) -> None:
    """M2-S5-P0: additive Protocol (D-M2-1)."""
    separator: VocalSeparator = FakeVocalSeparator()
    vocals, accompaniment = separator.separate(song, tmp_path / "stems")
    assert vocals.exists() and accompaniment.exists()


def test_fake_separator_writes_two_wavs_as_long_as_the_input(tmp_path: Path, song: Path) -> None:
    """M2-S5-P1: both stems are valid WAVs with the input's frame count."""
    vocals, accompaniment = FakeVocalSeparator().separate(song, tmp_path / "stems")
    assert vocals != accompaniment
    assert read_wav_info(vocals)[3] == read_wav_info(song)[3]
    assert read_wav_info(accompaniment)[3] == read_wav_info(song)[3]


def test_fake_separator_missing_input_fails_loudly(tmp_path: Path) -> None:
    """M2-S5-N0."""
    with pytest.raises(FileNotFoundError):
        FakeVocalSeparator().separate(tmp_path / "nope.wav", tmp_path / "stems")


# ---- Demucs adapter -------------------------------------------------------------------


def test_demucs_writes_vocals_and_accompaniment_into_out_dir(tmp_path: Path, song: Path) -> None:
    """M2-S5-P2: returns the two paths, both inside out_dir, both valid mono/stereo WAV."""
    out_dir = tmp_path / "stems"
    vocals, accompaniment = make(StubDemucs())[0].separate(song, out_dir)
    for path in (vocals, accompaniment):
        assert path.parent == out_dir
        assert read_wav_info(path)[2:] == (RATE, RATE)
    assert vocals != accompaniment


def test_demucs_creates_a_missing_out_dir(tmp_path: Path, song: Path) -> None:
    """M2-S5-E1."""
    out_dir = tmp_path / "a" / "b"
    make(StubDemucs())[0].separate(song, out_dir)
    assert out_dir.is_dir()


def test_demucs_loads_lazily_and_once(tmp_path: Path, song: Path) -> None:
    """M2-S5-P3 (D-M2-3)."""
    sep, factory = make(StubDemucs())
    assert factory.calls == 0
    sep.separate(song, tmp_path / "1")
    sep.separate(song, tmp_path / "2")
    assert factory.calls == 1


def test_demucs_same_input_twice_overwrites_cleanly(tmp_path: Path, song: Path) -> None:
    """M2-S5-E2: retry-safe, same out_dir reused."""
    sep, _ = make(StubDemucs())
    first = sep.separate(song, tmp_path / "s")
    second = sep.separate(song, tmp_path / "s")
    assert first == second
    assert leftovers(tmp_path / "s", {p.name for p in first}) == set()


def test_demucs_missing_input_fails_without_creating_files(tmp_path: Path) -> None:
    """M2-S5-N1."""
    sep, factory = make(StubDemucs())
    with pytest.raises(FileNotFoundError):
        sep.separate(tmp_path / "nope.wav", tmp_path / "stems")
    assert factory.calls == 0
    assert not (tmp_path / "stems").exists()


def test_demucs_empty_audio_file_is_a_coded_error(tmp_path: Path) -> None:
    """M2-S5-N2: a 0-byte file -> INTERNAL_ERROR, nothing written."""
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(DomainError) as info:
        make(StubDemucs())[0].separate(empty, tmp_path / "stems")
    assert info.value.code is FailureCode.INTERNAL_ERROR
    assert not (tmp_path / "stems").exists()


def test_demucs_zero_length_audio_gives_two_empty_stems_or_a_coded_error(
    tmp_path: Path,
) -> None:
    """M2-S5-E3: a valid WAV with no frames never crashes with a raw exception."""
    zero = write_wav(tmp_path / "z.wav", 0, RATE)
    try:
        vocals, accompaniment = make(StubDemucs(count=0))[0].separate(zero, tmp_path / "stems")
    except DomainError as exc:
        assert exc.code is FailureCode.INTERNAL_ERROR
        assert not (tmp_path / "stems").exists()
    else:
        assert read_wav_info(vocals)[3] == read_wav_info(accompaniment)[3] == 0


def test_demucs_model_crash_leaves_no_partial_stems(tmp_path: Path, song: Path) -> None:
    """M2-S5-N3."""
    with pytest.raises(DomainError) as info:
        make(StubDemucs(error=RuntimeError("mps oom")))[0].separate(song, tmp_path / "stems")
    assert info.value.code is FailureCode.INTERNAL_ERROR
    assert not list((tmp_path / "stems").glob("*")) if (tmp_path / "stems").exists() else True


def test_demucs_load_failure_is_a_model_load_error(tmp_path: Path, song: Path) -> None:
    """M2-S5-N4."""
    sep = DemucsSeparator(engine_factory=Factory(error=OSError("no weights")))
    with pytest.raises(ModelLoadError):
        sep.separate(song, tmp_path / "stems")


def test_demucs_timeout_raises_and_leaves_no_stems(tmp_path: Path, song: Path) -> None:
    """M2-S5-E4."""
    blocker = Blocker()
    sep, _ = make(StubDemucs(blocker=blocker), timeout_s=0.1)
    try:
        with pytest.raises(AdapterTimeoutError):
            sep.separate(song, tmp_path / "stems")
    finally:
        blocker.release.set()
    assert not list((tmp_path / "stems").glob("*")) if (tmp_path / "stems").exists() else True
