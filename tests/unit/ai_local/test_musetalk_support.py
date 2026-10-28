"""MuseTalk helpers: landmark cache, fingerprint, ffmpeg wrappers (real ffmpeg on tiny clips)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vidgen.infrastructure.local_ai import musetalk_support as support
from vidgen.infrastructure.local_ai.errors import LocalAiError

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg missing"
)
BOX = (10, 20, 110, 140)
FFMPEG, FFPROBE = "ffmpeg", "ffprobe"


def make_clip(path: Path, seconds: float = 2.0, *, audio: bool = True, fps: int = 30) -> Path:
    """A tiny synthetic clip (test pattern, optional sine tone)."""
    command = [
        FFMPEG, "-v", "error", "-y", "-f", "lavfi",
        "-i", f"testsrc=size=64x48:rate={fps}:duration={seconds}",
    ]  # fmt: skip
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    command += ["-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603
    return path


def probe(path: Path, entries: str, stream: str) -> str:
    """One ffprobe value."""
    out = subprocess.run(  # noqa: S603
        [FFPROBE, "-v", "error", "-select_streams", stream, "-show_entries", entries,
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return out.stdout.strip()


# ---- LandmarkCache ----------------------------------------------------------------------


def test_cache_miss_when_nothing_was_stored(tmp_path: Path) -> None:
    assert support.LandmarkCache(tmp_path).get("k", 3) is None


def test_cache_returns_what_was_stored(tmp_path: Path) -> None:
    cache = support.LandmarkCache(tmp_path)
    cache.put("k", [BOX, BOX, BOX])
    assert cache.get("k", 3) == [BOX, BOX, BOX]


def test_a_shorter_request_reuses_the_prefix(tmp_path: Path) -> None:
    cache = support.LandmarkCache(tmp_path)
    boxes = [(i, i, i + 10, i + 10) for i in range(5)]
    cache.put("k", boxes)
    assert cache.get("k", 2) == boxes[:2]


def test_a_longer_request_misses(tmp_path: Path) -> None:
    cache = support.LandmarkCache(tmp_path)
    cache.put("k", [BOX, BOX])
    assert cache.get("k", 3) is None


def test_different_keys_do_not_mix(tmp_path: Path) -> None:
    cache = support.LandmarkCache(tmp_path)
    cache.put("a", [BOX])
    assert cache.get("b", 1) is None


def test_corrupt_json_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / "k.json").write_text("{not json")
    assert support.LandmarkCache(tmp_path).get("k", 1) is None


@pytest.mark.parametrize("content", ["[[1, 2, 3]]", '"text"', '[[1, 2, 3, "x"]]', "null"])
def test_wrongly_shaped_json_is_a_miss(tmp_path: Path, content: str) -> None:
    (tmp_path / "k.json").write_text(content)
    assert support.LandmarkCache(tmp_path).get("k", 1) is None


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    support.LandmarkCache(tmp_path / "sub").put("k", [BOX, BOX])
    assert support.LandmarkCache(tmp_path / "sub").get("k", 2) == [BOX, BOX]


def test_put_leaves_no_partial_file_and_valid_json(tmp_path: Path) -> None:
    support.LandmarkCache(tmp_path).put("k", [BOX])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.json"]
    assert json.loads((tmp_path / "k.json").read_text()) == [list(BOX)]


def test_put_replaces_a_shorter_list_with_a_longer_one(tmp_path: Path) -> None:
    cache = support.LandmarkCache(tmp_path)
    cache.put("k", [BOX])
    cache.put("k", [BOX, BOX, BOX])
    assert support.LandmarkCache(tmp_path).get("k", 3) == [BOX] * 3


# ---- fingerprint ------------------------------------------------------------------------


def test_fingerprint_depends_on_content_not_path(tmp_path: Path) -> None:
    one, two = tmp_path / "one.mp4", tmp_path / "two.mp4"
    one.write_bytes(b"same bytes")
    two.write_bytes(b"same bytes")
    assert support.video_fingerprint(one) == support.video_fingerprint(two)


def test_fingerprint_changes_when_content_changes(tmp_path: Path) -> None:
    one, two = tmp_path / "one.mp4", tmp_path / "two.mp4"
    one.write_bytes(b"a")
    two.write_bytes(b"b")
    assert support.video_fingerprint(one) != support.video_fingerprint(two)


def test_fingerprint_of_an_empty_and_a_multichunk_file(tmp_path: Path) -> None:
    empty, big = tmp_path / "e", tmp_path / "b"
    empty.write_bytes(b"")
    big.write_bytes(b"x" * (support.FINGERPRINT_CHUNK * 2 + 5))
    assert len(support.video_fingerprint(empty)) == 64
    assert len(support.video_fingerprint(big)) == 64


def test_fingerprint_of_a_missing_file_raises_file_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        support.video_fingerprint(tmp_path / "nope")


# ---- run_tool ---------------------------------------------------------------------------


def test_run_tool_returns_stdout() -> None:
    assert support.run_tool([sys.executable, "-c", "print('hi')"]).strip() == "hi"


def test_run_tool_failure_is_a_local_ai_error_with_a_short_tail() -> None:
    code = "import sys; sys.stderr.write('E' * 5000 + 'THE-END'); sys.exit(3)"
    with pytest.raises(LocalAiError) as caught:
        support.run_tool([sys.executable, "-c", code])
    message = str(caught.value)
    assert "THE-END" in message
    assert len(message) < support.STDERR_TAIL_CHARS + 200


def test_run_tool_timeout_is_a_local_ai_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "TOOL_TIMEOUT_S", 0.2)
    with pytest.raises(LocalAiError, match="timed out"):
        support.run_tool([sys.executable, "-c", "import time; time.sleep(5)"])


# ---- ffmpeg wrappers --------------------------------------------------------------------


@needs_ffmpeg
def test_video_fps_reads_the_native_rate(tmp_path: Path) -> None:
    assert support.video_fps(make_clip(tmp_path / "c.mp4", fps=30)) == pytest.approx(30)


@needs_ffmpeg
def test_video_fps_of_a_non_video_is_a_local_ai_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(LocalAiError):
        support.video_fps(bad)


@needs_ffmpeg
def test_extract_frames_writes_numbered_pngs(tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()
    frames = support.extract_frames(make_clip(tmp_path / "c.mp4"), folder, 10)
    assert len(frames) == 10
    assert frames[0].name == "00000000.png"


@needs_ffmpeg
def test_extract_frames_from_a_corrupt_video_is_a_local_ai_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"garbage")
    folder = tmp_path / "f"
    folder.mkdir()
    with pytest.raises(LocalAiError):
        support.extract_frames(bad, folder, 5)


@needs_ffmpeg
def test_assemble_video_keeps_duration_and_audio(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4", seconds=2.0)
    frames = tmp_path / "frames"
    frames.mkdir()
    support.extract_frames(clip, frames, 10)  # stand-in for the blended head (10 frames = 0.4 s)
    out = tmp_path / "out.mp4"
    support.assemble_video(frames, 10, clip, out)
    assert float(probe(out, "format=duration", "v:0")) == pytest.approx(2.0, abs=0.15)
    assert probe(out, "stream=codec_type", "a:0") == "audio"
    assert float(support.video_fps(out)) == pytest.approx(30, abs=0.5)


@needs_ffmpeg
def test_assemble_video_works_for_a_template_without_audio(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4", seconds=1.0, audio=False)
    frames = tmp_path / "frames"
    frames.mkdir()
    support.extract_frames(clip, frames, 5)
    out = tmp_path / "out.mp4"
    support.assemble_video(frames, 5, clip, out)
    assert out.exists()
    assert probe(out, "stream=codec_type", "a:0") == ""


@needs_ffmpeg
def test_assemble_video_with_missing_frames_is_a_local_ai_error(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "c.mp4")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(LocalAiError):
        support.assemble_video(empty, 5, clip, tmp_path / "out.mp4")
