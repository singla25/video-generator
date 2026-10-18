"""Engine failure handling: typed errors, timeouts, no partial output, no shell (ADR-004)."""

from __future__ import annotations

import stat
import tempfile
import time
from pathlib import Path

import pytest

from tests.fixtures.spies import record_popen
from tests.fixtures.templates import make_label_png, make_tone_wav
from tests.integration.ffmpeg.conftest import DEFAULT_METADATA, RenderFn
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.domain.timing import TimingRules, plan_timing
from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder

SLOT = (1.0, 2.0)


def script(path: Path, body: str) -> str:
    """Create an executable stand-in for ffmpeg and return its path."""
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class Inputs:
    """Valid inputs for direct encoder calls."""

    def __init__(self, work: Path, template: Path) -> None:
        self.template = template
        self.audio = make_tone_wav(work / "new.wav", 1.0)
        self.label = make_label_png(work / "label.png", 320, 24)
        self.plan = plan_timing(1.0, 0.6, 1.0, TimingRules())
        self.out = work / "out.mp4"

    def render(self, encoder: FfmpegVideoEncoder) -> None:
        """Call the encoder with these inputs."""
        encoder.render(
            self.template, self.audio, SLOT, self.plan, self.label, DEFAULT_METADATA, self.out
        )


@pytest.fixture
def inputs(tmp_path: Path, shared_template: Path) -> Inputs:
    """Inputs placed in an otherwise empty work folder."""
    work = tmp_path / "work"
    work.mkdir()
    return Inputs(work, shared_template)


def listing(folder: Path) -> list[str]:
    """Sorted names of everything in ``folder``."""
    return sorted(p.name for p in folder.iterdir())


# ---- failures -------------------------------------------------------------------------


def test_nonzero_exit_becomes_a_typed_internal_error_with_no_output(
    tmp_path: Path, inputs: Inputs
) -> None:
    """Row render crash: ffmpeg exits 1 after touching its output file."""
    fake = script(
        tmp_path / "fake_ffmpeg", 'for last; do :; done\necho partial > "$last"\nexit 1\n'
    )
    before = listing(inputs.out.parent)
    with pytest.raises(DomainError) as info:
        inputs.render(FfmpegVideoEncoder(ffmpeg_path=fake, timeout_seconds=10.0))
    assert info.value.code is FailureCode.INTERNAL_ERROR
    assert listing(inputs.out.parent) == before  # no partial output, no temp file left


def test_error_message_is_plain_and_does_not_dump_command_or_paths(
    tmp_path: Path, inputs: Inputs
) -> None:
    """TT-AC17-E10: file names and ffmpeg stderr stay out of the user-facing message."""
    fake = script(
        tmp_path / "fake_ffmpeg", 'echo "Error opening ' + str(inputs.audio) + '" >&2\nexit 1\n'
    )
    with pytest.raises(DomainError) as info:
        inputs.render(FfmpegVideoEncoder(ffmpeg_path=fake, timeout_seconds=10.0))
    assert str(inputs.audio) not in info.value.message
    assert "Error opening" not in info.value.message


def test_hanging_ffmpeg_is_killed_and_reported_as_render_timeout(
    tmp_path: Path, inputs: Inputs
) -> None:
    """TT-AC12-P3, E1 (B8): timeout -> RENDER_TIMEOUT, process killed, no leftovers."""
    fake = script(tmp_path / "slow_ffmpeg", 'for last; do :; done\necho x > "$last"\nsleep 30\n')
    before = listing(inputs.out.parent)
    started = time.perf_counter()
    with pytest.raises(DomainError) as info:
        inputs.render(FfmpegVideoEncoder(ffmpeg_path=fake, timeout_seconds=0.5))
    assert info.value.code is FailureCode.RENDER_TIMEOUT
    assert time.perf_counter() - started < 10
    assert listing(inputs.out.parent) == before


def test_missing_ffmpeg_binary_is_an_internal_error(tmp_path: Path, inputs: Inputs) -> None:
    """TT-AC1-E7 analogue for the engine."""
    with pytest.raises(DomainError) as info:
        inputs.render(FfmpegVideoEncoder(ffmpeg_path=str(tmp_path / "nope"), timeout_seconds=5.0))
    assert info.value.code is FailureCode.INTERNAL_ERROR


@pytest.mark.parametrize("which", ["audio", "label", "template"])
def test_unreadable_inputs_fail_cleanly_with_the_real_ffmpeg(
    encoder: FfmpegVideoEncoder, inputs: Inputs, which: str
) -> None:
    """TT-AC10-N2: corrupt or missing inputs -> typed error and no unlabelled/partial output."""
    broken = inputs.out.parent / "broken.bin"
    broken.write_bytes(b"not media at all")
    if which == "audio":
        inputs.audio = broken
    elif which == "label":
        inputs.label = inputs.out.parent / "missing.png"
    else:
        inputs.template = broken
    before = listing(inputs.out.parent)
    with pytest.raises(DomainError) as info:
        inputs.render(encoder)
    assert info.value.code is FailureCode.INTERNAL_ERROR
    assert listing(inputs.out.parent) == before


def test_existing_output_is_never_overwritten(encoder: FfmpegVideoEncoder, inputs: Inputs) -> None:
    """AC11 / AC12-P6: an existing output file is left untouched."""
    inputs.out.write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        inputs.render(encoder)
    assert inputs.out.read_bytes() == b"precious"


def test_temp_files_are_removed_on_success_and_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, encoder: FfmpegVideoEncoder, inputs: Inputs
) -> None:
    """TT-AC12-P5, N4: intermediate files live in the temp dir and are gone afterwards."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    inputs.render(encoder)
    assert list(scratch.iterdir()) == []
    inputs.out.unlink()
    inputs.audio = inputs.out.parent / "broken.bin"
    inputs.audio.write_bytes(b"junk")
    with pytest.raises(DomainError):
        inputs.render(encoder)
    assert list(scratch.iterdir()) == []


# ---- command construction -------------------------------------------------------------


def test_commands_are_argument_lists_without_a_shell(
    monkeypatch: pytest.MonkeyPatch, render_clip: RenderFn, ffmpeg_path: str
) -> None:
    """ADR-004: no shell, no command strings (spy on Popen, used by every subprocess call)."""
    calls = record_popen(monkeypatch)
    render_clip()
    assert calls
    for call in calls:
        assert isinstance(call.args, list)
        assert all(isinstance(item, str) for item in call.args)
        assert not call.kwargs.get("shell")
    assert any(call.args[0] == ffmpeg_path for call in calls)


def test_hostile_looking_file_and_metadata_text_cannot_inject_arguments(
    tmp_path: Path, render_clip: RenderFn
) -> None:
    """ADR-004: values with quotes, semicolons and leading dashes stay data."""
    r = render_clip(
        metadata={
            "creator_entity": "-y; rm -rf x $(id) 'q' \"d\"",
            "generated_on": "2026-10-18",
            "batch_id": "--help",
        }
    )
    assert r.out.exists() and r.out.stat().st_size > 0
    assert not (tmp_path / "x").exists()
