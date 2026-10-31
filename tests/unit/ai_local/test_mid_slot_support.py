"""DD-39 part B: lip sync starts at the slot. Pure cache key and real ffmpeg on tiny clips.

The clips are generated here (testsrc2 picture, sine tone, solid red frames). Nothing loads a
model. Test tree IDs: ML-F-* (landmark_key), ML-X-* (extract_frames), ML-A-* (assemble_video),
see docs/test-tree/mid-slot-lipsync.md.
"""

from __future__ import annotations

import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from vidgen.infrastructure.local_ai import musetalk_support as support
from vidgen.infrastructure.local_ai.errors import LocalAiError

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg missing"
)
FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
WIDTH, HEIGHT = 160, 120
FPS = 25
SECONDS = 4.0
FRAME_BYTES = WIDTH * HEIGHT * 3
RED_FRAMES = 5  # 0.2 s of MuseTalk output at 25 fps


# ---- helpers ------------------------------------------------------------------------------


def run(command: list[str]) -> bytes:
    """Run a tool with a fixed argument list and return its stdout."""
    done = subprocess.run(command, check=True, capture_output=True)  # noqa: S603
    return done.stdout


def make_video(path: Path) -> Path:
    """4 s, 25 fps test pattern with a 440 Hz tone (AAC)."""
    run([
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FPS}:duration={SECONDS}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={SECONDS}",
        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", str(path),
    ])  # fmt: skip
    return path


def make_red_frames(folder: Path, count: int = RED_FRAMES) -> Path:
    """``count`` solid red PNG frames named %08d.png, the same size as the video."""
    folder.mkdir(parents=True, exist_ok=True)
    run([
        FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:s={WIDTH}x{HEIGHT}",
        "-frames:v", str(count), "-start_number", "0", str(folder / "%08d.png"),
    ])  # fmt: skip
    return folder


def grab(video: Path, at_s: float) -> bytes:
    """The frame at ``at_s`` as raw RGB bytes, decoded by ffmpeg (seek before the input)."""
    data = run([
        FFMPEG, "-v", "error", "-ss", f"{at_s:.6f}", "-i", str(video),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])  # fmt: skip
    assert len(data) == FRAME_BYTES, f"no frame at {at_s} s in {video.name}"
    return data


def decode_png(path: Path) -> bytes:
    """A PNG frame as raw RGB bytes."""
    return run([
        FFMPEG, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])  # fmt: skip


def mean_abs_diff(first: bytes, second: bytes) -> float:
    """Mean absolute difference per byte on the 0-255 scale."""
    assert len(first) == len(second) == FRAME_BYTES
    return sum(abs(a - b) for a, b in zip(first, second, strict=True)) / len(first)


def channel_means(rgb: bytes) -> tuple[float, float, float]:
    """Mean R, G and B of a raw RGB frame."""
    count = len(rgb) // 3
    return (sum(rgb[0::3]) / count, sum(rgb[1::3]) / count, sum(rgb[2::3]) / count)


def is_red(rgb: bytes) -> bool:
    """Clearly red: R high, G and B low."""
    red, green, blue = channel_means(rgb)
    return red > 200 and green < 60 and blue < 60


def probe(path: Path, entries: str, stream: str | None = None) -> str:
    """One ffprobe value, optionally for one stream selector."""
    command = [FFPROBE, "-v", "error"]
    if stream is not None:
        command += ["-select_streams", stream]
    command += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    return run(command).decode().strip()


def duration_s(path: Path) -> float:
    """Container duration in seconds."""
    return float(probe(path, "format=duration"))


def audio_seconds(path: Path) -> float:
    """Decoded length of the audio stream (counted from samples, not metadata)."""
    rate = 8000
    pcm = run([
        FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1",
        "-ar", str(rate), "-f", "s16le", "-",
    ])  # fmt: skip
    return len(pcm) / 2 / rate


# ---- landmark_key -------------------------------------------------------------------------


def test_zero_start_keeps_the_fingerprint_unchanged() -> None:
    """ML-F-P1: today's cache key for a template is not renamed."""
    assert support.landmark_key("abc123", 0.0) == "abc123"


def test_a_start_of_two_and_a_half_seconds_appends_milliseconds() -> None:
    """ML-F-P2: 2.5 s -> suffix -s2500."""
    assert support.landmark_key("abc123", 2.5) == "abc123-s2500"


@pytest.mark.parametrize(("start", "suffix"), [(1.0, "-s1000"), (10.0, "-s10000")])
def test_whole_second_starts_use_the_same_millisecond_suffix(start: float, suffix: str) -> None:
    """ML-F-P3."""
    assert support.landmark_key("abc123", start) == f"abc123{suffix}"


def test_different_starts_give_different_keys() -> None:
    """ML-F-E1: 1.2 s and 1.3 s need different face boxes, so different keys."""
    assert support.landmark_key("abc123", 1.2) != support.landmark_key("abc123", 1.3)


def test_the_same_start_always_gives_the_same_key() -> None:
    """ML-F-E2: a second render of the same template and start reuses the cache."""
    assert support.landmark_key("abc123", 2.5) == support.landmark_key("abc123", 2.5)


# ---- extract_frames (real ffmpeg) ---------------------------------------------------------


@needs_ffmpeg
def test_extract_from_two_seconds_starts_at_that_frame(tmp_path: Path) -> None:
    """ML-X-P1: five frames, the first is the frame at 2.0 s."""
    video = make_video(tmp_path / "in.mp4")
    folder = tmp_path / "frames"
    folder.mkdir()
    frames = support.extract_frames(video, folder, 5, start_s=2.0)
    assert len(frames) == 5
    assert mean_abs_diff(decode_png(frames[0]), grab(video, 2.0)) < 2


@needs_ffmpeg
def test_extract_from_zero_starts_at_the_first_frame(tmp_path: Path) -> None:
    """ML-X-P2: start 0.0 is today's behaviour, the first frame is the frame at 0 s."""
    video = make_video(tmp_path / "in.mp4")
    folder = tmp_path / "frames"
    folder.mkdir()
    frames = support.extract_frames(video, folder, 5, start_s=0.0)
    assert len(frames) == 5
    assert mean_abs_diff(decode_png(frames[0]), grab(video, 0.0)) < 2


@needs_ffmpeg
def test_extract_beyond_the_end_is_a_local_ai_error(tmp_path: Path) -> None:
    """ML-X-N1: no frame can be read at 10 s of a 4 s video."""
    video = make_video(tmp_path / "in.mp4")
    folder = tmp_path / "frames"
    folder.mkdir()
    with pytest.raises(LocalAiError):
        support.extract_frames(video, folder, 5, start_s=10.0)


@needs_ffmpeg
def test_extract_near_the_end_returns_what_exists_without_error(tmp_path: Path) -> None:
    """ML-X-E1: five frames from 3.9 s run past the end; the frames that exist are returned."""
    video = make_video(tmp_path / "in.mp4")
    folder = tmp_path / "frames"
    folder.mkdir()
    frames = support.extract_frames(video, folder, 5, start_s=3.9)
    assert 1 <= len(frames) <= 5


# ---- assemble_video (real ffmpeg) ---------------------------------------------------------


@pytest.fixture
def assembled_from_two_seconds(tmp_path: Path) -> tuple[Path, Path]:
    """The original video and the output of assemble_video with red frames at 2.0 s."""
    video = make_video(tmp_path / "in.mp4")
    blended = make_red_frames(tmp_path / "blended")
    out = tmp_path / "out.mp4"
    support.assemble_video(blended, RED_FRAMES, video, out, start_s=2.0)
    return video, out


@needs_ffmpeg
def test_assembled_output_keeps_the_original_length(
    assembled_from_two_seconds: tuple[Path, Path],
) -> None:
    """ML-A-P1: 2.0 s head + 0.2 s blended + 1.8 s tail = 4.0 s."""
    video, out = assembled_from_two_seconds
    assert abs(duration_s(out) - duration_s(video)) < 0.1


@needs_ffmpeg
def test_frame_before_the_slot_is_the_original(
    assembled_from_two_seconds: tuple[Path, Path],
) -> None:
    """ML-A-P2: 0 to start_s is copied from the original."""
    video, out = assembled_from_two_seconds
    assert mean_abs_diff(grab(out, 1.0), grab(video, 1.0)) < 3


@needs_ffmpeg
def test_frame_inside_the_slot_is_the_blended_red_frame(
    assembled_from_two_seconds: tuple[Path, Path],
) -> None:
    """ML-A-P3: 2.0 s to 2.2 s carries the blended frames."""
    _, out = assembled_from_two_seconds
    assert is_red(grab(out, 2.1))


@needs_ffmpeg
def test_frame_after_the_slot_is_the_original_at_the_same_time(
    assembled_from_two_seconds: tuple[Path, Path],
) -> None:
    """ML-A-P4: the tail is placed back at its own time, so the audio stays in step."""
    video, out = assembled_from_two_seconds
    assert mean_abs_diff(grab(out, 3.0), grab(video, 3.0)) < 3


@needs_ffmpeg
def test_audio_is_kept_with_the_original_length(
    assembled_from_two_seconds: tuple[Path, Path],
) -> None:
    """ML-A-P5: the original audio is copied unchanged."""
    video, out = assembled_from_two_seconds
    assert probe(out, "stream=codec_type", "a:0") == "audio"
    assert abs(audio_seconds(out) - audio_seconds(video)) < 0.1


@needs_ffmpeg
def test_zero_start_keeps_the_old_order_red_head_then_the_original(tmp_path: Path) -> None:
    """ML-A-P6: start 0.0 is today's output: blended frames first, then the rest."""
    video = make_video(tmp_path / "in.mp4")
    blended = make_red_frames(tmp_path / "blended")
    out = tmp_path / "out.mp4"
    support.assemble_video(blended, RED_FRAMES, video, out, start_s=0.0)
    assert is_red(grab(out, 0.0))
    assert is_red(grab(out, 0.1))
    assert mean_abs_diff(grab(out, 1.0), grab(video, 1.0)) < 3


@needs_ffmpeg
def test_slot_that_runs_past_the_end_has_no_third_part_and_no_error(tmp_path: Path) -> None:
    """ML-A-E1: the blended part is cut at the original end (4.0 s).

    Start 3.9 s plus 0.2 s of red would run to 4.1 s. The output keeps the original duration:
    no error, length within 0.1 s of 4.0, the red frame is still there at 3.95 s.
    """
    video = make_video(tmp_path / "in.mp4")
    blended = make_red_frames(tmp_path / "blended")
    out = tmp_path / "out.mp4"
    support.assemble_video(blended, RED_FRAMES, video, out, start_s=3.9)
    assert abs(duration_s(out) - 4.0) <= 0.1
    assert is_red(grab(out, 3.95))


@needs_ffmpeg
@pytest.mark.parametrize("start_s", [0.0, 2.0])
def test_video_keeps_the_original_frame_rate_and_size(tmp_path: Path, start_s: float) -> None:
    """ML-A-E2: fps, width and height of the input are kept."""
    video = make_video(tmp_path / "in.mp4")
    blended = make_red_frames(tmp_path / "blended")
    out = tmp_path / "out.mp4"
    support.assemble_video(blended, RED_FRAMES, video, out, start_s=start_s)
    assert Fraction(probe(out, "stream=avg_frame_rate", "v:0")) == FPS
    assert probe(out, "stream=width,height", "v:0").split() == [str(WIDTH), str(HEIGHT)]
