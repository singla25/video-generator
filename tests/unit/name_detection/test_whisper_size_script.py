"""``backend/scripts/whisper_size_test.py``: offline model-size table (AC7)."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.unit.ai_local.conftest import write_wav

SCRIPT = Path(__file__).resolve().parents[3] / "backend" / "scripts" / "whisper_size_test.py"


class W:
    def __init__(self, word: str, start: float, end: float, probability: float) -> None:
        self.word, self.start, self.end, self.probability = word, start, end, probability


class Seg:
    def __init__(self, words: list[W]) -> None:
        self.words = words


class StubModel:
    def __init__(self, heard: list[W]) -> None:
        self.heard = heard

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[list[Seg], object]:
        return [Seg(self.heard)], object()


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("whisper_size_test", SCRIPT)
    assert spec is not None and spec.loader is not None, f"missing {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_loader(weights_dir: Path) -> StubModel:
    """small hears the name in Devanagari; medium hears nothing close."""
    if weights_dir.name == "small":
        return StubModel([W("कृष्ण", 0.0, 0.4, 0.9)])
    return StubModel([W("Zzzz", 0.0, 0.4, 0.9)])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for size in ("small", "medium"):
        (tmp_path / "weights" / size).mkdir(parents=True)
        (tmp_path / "weights" / size / "model.bin").write_bytes(b"x")
    return tmp_path / "weights"


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "demo.wav")


def run(argv: list[str]) -> int:
    return int(load_script().main(argv, loader=stub_loader))


# ---- positive -------------------------------------------------------------------------


def test_prints_one_row_per_size_with_found_closeness_and_candidates(
    root: Path, audio: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(["--weights-root", str(root), "--name", "Krishan", "--audio", str(audio)])
    out = capsys.readouterr().out
    assert code == 0
    small = next(line for line in out.splitlines() if line.lstrip().startswith("small"))
    medium = next(line for line in out.splitlines() if line.lstrip().startswith("medium"))
    assert "yes" in small and "no" in medium
    assert "कृष्ण" in small  # the heard word is listed
    assert any(ch.isdigit() for ch in small)  # seconds / memory / closeness
    assert "closeness" in out.lower() and "memory" in out.lower()


def test_several_audio_files_are_all_tried(
    root: Path, audio: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = write_wav(tmp_path / "second.wav")
    code = run(
        [
            "--weights-root",
            str(root),
            "--name",
            "Krishan",
            "--audio",
            str(audio),
            "--audio",
            str(second),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("small") >= 2 and out.count("medium") >= 2


def test_makes_no_network_call(root: Path, audio: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_a: Any, **_k: Any) -> None:
        raise AssertionError("network used")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    assert run(["--weights-root", str(root), "--name", "Krishan", "--audio", str(audio)]) == 0


def test_writes_nothing_into_the_weights_folder(root: Path, audio: Path) -> None:
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    run(["--weights-root", str(root), "--name", "Krishan", "--audio", str(audio)])
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


# ---- negative -------------------------------------------------------------------------


def test_missing_weights_folder_exits_two_with_a_clear_message(
    tmp_path: Path, audio: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = tmp_path / "nope"
    code = run(["--weights-root", str(gone), "--name", "Krishan", "--audio", str(audio)])
    assert code == 2
    assert str(gone) in capsys.readouterr().err


def test_missing_audio_file_exits_two_with_a_clear_message(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = tmp_path / "missing.wav"
    code = run(["--weights-root", str(root), "--name", "Krishan", "--audio", str(gone)])
    assert code == 2
    assert str(gone) in capsys.readouterr().err


def test_weights_folder_without_size_subfolders_exits_two(tmp_path: Path, audio: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run(["--weights-root", str(empty), "--name", "Krishan", "--audio", str(audio)]) == 2


def test_missing_required_arguments_exit_two(root: Path) -> None:
    with pytest.raises(SystemExit) as info:
        load_script().main(["--weights-root", str(root)], loader=stub_loader)
    assert info.value.code == 2


# ---- edge -----------------------------------------------------------------------------


def test_silent_audio_gives_not_found_rows_without_crashing(
    root: Path, audio: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def silent(_dir: Path) -> StubModel:
        return StubModel([])

    code = load_script().main(
        ["--weights-root", str(root), "--name", "Krishan", "--audio", str(audio)], loader=silent
    )
    assert code == 0
    assert "no" in capsys.readouterr().out
