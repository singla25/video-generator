"""Synthetic media generators using ffmpeg lavfi. Code only; nothing here is a real sample."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# codec name -> (encoder args)
_VIDEO_ARGS: dict[str, list[str]] = {
    "h264": ["-c:v", "libx264", "-preset", "ultrafast"],
    "hevc": ["-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1"],
    "mpeg4": ["-c:v", "mpeg4"],
    "vp9": ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8"],
}
_AUDIO_ARGS: dict[str, list[str]] = {
    "aac": ["-c:a", "aac"],
    "opus": ["-c:a", "libopus"],
}


def make_video(
    path: Path,
    *,
    seconds: float = 2.0,
    size: tuple[int, int] = (320, 240),
    fps: int = 25,
    vcodec: str = "h264",
    acodec: str | None = "aac",
    pix_fmt: str = "yuv420p",
    container: str | None = None,
    title: str | None = None,
) -> Path:
    """Generate a small test video at ``path`` (format chosen by suffix or ``container``).

    ``acodec=None`` produces a file without an audio track. The picture is ``testsrc2`` and
    the sound is a sine tone, so frames and samples are non-trivial.
    """
    width, height = size
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}:duration={seconds}",
    ]  # fmt: skip
    if acodec is not None:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={seconds}"]
    cmd += _VIDEO_ARGS[vcodec] + ["-pix_fmt", pix_fmt]
    if acodec is None:
        cmd += ["-an"]
    else:
        cmd += _AUDIO_ARGS[acodec] + ["-ac", "1"]
    if title is not None:
        cmd += ["-metadata", f"title={title}"]
    if container is not None:
        cmd += ["-f", container]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)  # noqa: S603
    return path


def make_audio_only_mp4(path: Path, *, seconds: float = 2.0) -> Path:
    """Generate an MP4 container that holds only an audio stream."""
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={seconds}",
        "-c:a", "aac", "-f", "mp4", str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)  # noqa: S603
    return path


def truncate_copy(source: Path, target: Path, keep_fraction: float = 0.3) -> Path:
    """Write the first ``keep_fraction`` of ``source``'s bytes to ``target``."""
    data = source.read_bytes()
    target.write_bytes(data[: max(1, int(len(data) * keep_fraction))])
    return target
