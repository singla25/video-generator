"""Tiny synthetic clips for the output quality checker (real ffmpeg, 160x120, 1-4 s)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.fixtures.media import FFMPEG

SIZE = (160, 120)
FPS = 25
BASE_SECONDS = 3.0
SLOT = (1.0, 2.0)


def make_clip(
    path: Path,
    *,
    seconds: float = BASE_SECONDS,
    size: tuple[int, int] = SIZE,
    fps: int = FPS,
    vcodec: str = "libx264",
    audio: str | None = "tone",
    sample_rate: int = 16000,
    channels: int = 1,
    gain_db: float = 0.0,
    gain_region: tuple[float, float] = SLOT,
) -> Path:
    """Write an MP4: test picture plus a steady tone, silence (``audio="silent"``) or no audio.

    ``gain_db`` raises or lowers the tone only inside ``gain_region``; a steady tone makes the
    loudness of any region predictable, whatever the clip length.
    """
    width, height = size
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "lavfi"]
    cmd += ["-i", f"testsrc2=size={width}x{height}:rate={fps}:duration={seconds}"]
    if audio == "tone":
        start, end = gain_region
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate={sample_rate}:duration={seconds}",
        ]
        cmd += ["-af", f"volume=-18dB,volume=enable='between(t,{start},{end})':volume={gain_db}dB"]
    elif audio == "silent":
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono:d={seconds}"]
    cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p"]
    cmd += ["-preset", "ultrafast"] if vcodec == "libx264" else []
    cmd += ["-c:a", "aac", "-ac", str(channels)] if audio else ["-an"]
    # Explicit container so a misleading extension (e.g. ".bin") still gets a real MP4 inside.
    cmd += ["-t", str(seconds), "-f", "mp4", str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)  # noqa: S603
    return path
