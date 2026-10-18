"""Template videos with a 'name slot', plus synthetic replacement audio and label images."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from tests.fixtures.media import FFMPEG

SLOT = (1.0, 2.0)  # seconds: the spoken name (880 Hz tone)
PAUSE_S = 0.6  # silence right after the slot, then speech (440 Hz) resumes
TEMPLATE_SECONDS = 4.0

_SPEECH_EXPR = "if(between(t,1,2),0.3*sin(2*PI*880*t),if(between(t,2,2.6),0,0.3*sin(2*PI*440*t)))"

_VIDEO_ENC = {
    "h264": ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"],
    "hevc": ["-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"],
}


def make_template(
    path: Path,
    *,
    seconds: float = TEMPLATE_SECONDS,
    size: tuple[int, int] = (320, 240),
    fps: int = 25,
    vcodec: str = "h264",
    sample_rate: int = 16000,
    channels: int = 1,
    container: str | None = None,
) -> Path:
    """Template video: moving test picture + speech-like audio with a slot and a pause.

    Audio: 440 Hz speech, an 880 Hz "name" at 1.0-2.0 s, silence 2.0-2.6 s (the pause).
    """
    width, height = size
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}:duration={seconds}",
        "-f", "lavfi", "-i", f"aevalsrc='{_SPEECH_EXPR}':s={sample_rate}:d={seconds}",
        *_VIDEO_ENC[vcodec], "-c:a", "aac", "-b:a", "128k", "-ac", str(channels),
    ]  # fmt: skip
    if container is not None:
        cmd += ["-f", container]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)  # noqa: S603
    return path


def make_tone_wav(
    path: Path,
    seconds: float,
    *,
    amplitude: float = 0.3,
    freq: float = 660.0,
    sample_rate: int = 16000,
    channels: int = 1,
    cosine: bool = False,
) -> Path:
    """Write a synthetic 'new name' recording (a tone) as WAV.

    ``cosine=True`` starts and ends at high amplitude, so a hard cut would click.
    """
    wave = "cos" if cosine else "sin"
    expr = f"{amplitude}*{wave}(2*PI*{freq}*t)"
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"aevalsrc='{expr}':s={sample_rate}:d={seconds}",
        "-ac", str(channels), "-c:a", "pcm_s16le", str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)  # noqa: S603
    return path


def make_label_png(path: Path, width: int, band_height: int) -> Path:
    """A synthetic opaque label: dark band with a light bar in the middle (no fonts needed)."""
    image = Image.new("RGB", (width, band_height), (20, 20, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (width // 4, band_height // 4, 3 * width // 4, 3 * band_height // 4), fill=(235, 235, 235)
    )
    image.save(path, "PNG")
    return path
