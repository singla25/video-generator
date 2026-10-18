"""Measurement helpers for rendered media: ffprobe JSON, PCM, loudness, frames."""

from __future__ import annotations

import array
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
PCM_RATE = 16000


def probe_json(path: Path) -> dict[str, Any]:
    """Return ffprobe's format + streams as a dict."""
    out = subprocess.run(  # noqa: S603
        [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    data: dict[str, Any] = json.loads(out)
    return data


def stream(path: Path, kind: str) -> dict[str, Any]:
    """The first stream of ``kind`` ('video' or 'audio')."""
    for item in probe_json(path)["streams"]:
        if item["codec_type"] == kind:
            result: dict[str, Any] = item
            return result
    raise AssertionError(f"no {kind} stream in {path}")


def stream_kinds(path: Path) -> list[str]:
    """Codec types of all streams, in order."""
    return [str(item["codec_type"]) for item in probe_json(path)["streams"]]


def fps_of(path: Path) -> float:
    """Frame rate of the video stream."""
    num, den = str(stream(path, "video")["r_frame_rate"]).split("/")
    return int(num) / int(den)


def duration_of(path: Path) -> float:
    """Container duration in seconds."""
    return float(probe_json(path)["format"]["duration"])


def format_tags(path: Path) -> dict[str, str]:
    """Container-level metadata tags, keys lower-cased."""
    tags = probe_json(path)["format"].get("tags", {})
    return {k.lower(): v for k, v in tags.items()}


def frame_count(path: Path) -> int:
    """Number of decoded video frames."""
    out = subprocess.run(  # noqa: S603
        [FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, timeout=120,
    ).stdout  # fmt: skip
    return int(out.decode().strip().rstrip(","))


def decode_pcm(path: Path) -> array.array[int]:
    """Decode the audio to mono 16 kHz signed 16-bit samples."""
    raw = subprocess.run(  # noqa: S603
        [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-f", "s16le",
         "-ac", "1", "-ar", str(PCM_RATE), "-"],
        check=True, capture_output=True, timeout=120,
    ).stdout  # fmt: skip
    samples: array.array[int] = array.array("h")
    samples.frombytes(raw)
    return samples


def window(samples: array.array[int], start_s: float, end_s: float) -> list[int]:
    """Samples between two times (seconds), clipped to the signal."""
    first = max(0, int(start_s * PCM_RATE))
    last = min(len(samples), int(end_s * PCM_RATE))
    return list(samples[first:last])


def rms_dbfs(values: list[int]) -> float:
    """RMS level in dB relative to full scale (-inf for silence)."""
    if not values:
        raise ValueError("empty window")
    mean_square = sum(v * v for v in values) / len(values)
    return 10 * math.log10(mean_square / 32768**2) if mean_square else float("-inf")


def diff_dbfs(a: list[int], b: list[int]) -> float:
    """RMS level of (a - b) in dBFS; windows must have the same length."""
    if len(a) != len(b) or not a:
        raise ValueError(f"window sizes differ or are empty: {len(a)} vs {len(b)}")
    return rms_dbfs([x - y for x, y in zip(a, b, strict=True)])


def max_step(values: list[int]) -> float:
    """Largest sample-to-sample jump as a fraction of full scale (click detector)."""
    return max(abs(values[i + 1] - values[i]) for i in range(len(values) - 1)) / 32768


def loudness_lufs(path: Path, start_s: float, end_s: float) -> float:
    """Integrated loudness (EBU R128) of a time range, measured with ffmpeg ebur128."""
    result = subprocess.run(  # noqa: S603
        [FFMPEG, "-hide_banner", "-nostats", "-ss", str(start_s), "-t", str(end_s - start_s),
         "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120, check=True,
    )  # fmt: skip
    found = re.findall(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", result.stderr)
    if not found:
        raise AssertionError("ebur128 produced no integrated loudness")
    return float(found[-1])


def extract_frame(path: Path, at_s: float, out_png: Path) -> Image.Image:
    """Decode the frame at ``at_s`` to a PNG and return it as an RGB image."""
    subprocess.run(  # noqa: S603
        [FFMPEG, "-y", "-v", "error", "-ss", str(at_s), "-i", str(path),
         "-frames:v", "1", str(out_png)],
        check=True, capture_output=True, timeout=60,
    )  # fmt: skip
    return Image.open(out_png).convert("RGB")


def mean_abs_diff(a: Image.Image, b: Image.Image, box: tuple[int, int, int, int]) -> float:
    """Mean absolute pixel difference (0-255) between two images inside ``box``."""
    diff = ImageChops.difference(a.crop(box), b.crop(box))
    return sum(ImageStat.Stat(diff).mean) / 3


def frame_hashes(path: Path, *, skip_top: int = 0) -> list[str]:
    """MD5 of every video frame below the top ``skip_top`` rows (frame-by-frame content id)."""
    vf = f"crop=iw:ih-{skip_top}:0:{skip_top}" if skip_top else "null"
    out = subprocess.run(  # noqa: S603
        [FFMPEG, "-v", "error", "-i", str(path), "-an", "-vf", vf, "-f", "framemd5", "-"],
        check=True, capture_output=True, timeout=300, text=True,
    ).stdout  # fmt: skip
    return [ln.split(",")[-1].strip() for ln in out.splitlines() if ln and not ln.startswith("#")]


def longest_run(values: list[str]) -> int:
    """Length of the longest run of identical consecutive items."""
    best = run = 0
    previous: str | None = None
    for value in values:
        run = run + 1 if value == previous else 1
        previous = value
        best = max(best, run)
    return best


def pixel_mean(image: Image.Image, xy: tuple[int, int]) -> float:
    """Average of the colour channels (alpha excluded) at one pixel."""
    pixel = image.getpixel(xy)
    assert isinstance(pixel, tuple)
    channels = pixel[:3]
    return sum(channels) / len(channels)


def active_end(
    samples: array.array[int], start_s: float, limit_s: float, threshold_dbfs: float = -35.0
) -> float:
    """Time where sound that is present at ``start_s`` first drops below the threshold.

    Uses 10 ms windows; returns ``limit_s`` if the sound never stops before the limit.
    """
    step = 0.01
    at = start_s
    while at < limit_s:
        chunk = window(samples, at, at + step)
        if not chunk or rms_dbfs(chunk) < threshold_dbfs:
            return at
        at += step
    return limit_s
