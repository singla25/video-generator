"""MuseTalk helpers without heavy imports: ffmpeg calls, template fingerprint, landmark cache.

Memory note (measured in the M2 spike, RESULTS.md): one MuseTalk render peaks at 16-18 GB on
the 24 GB Mac, so only one runs at a time (``SingleRenderGuard``) and the models stay loaded
between renders instead of being rebuilt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
from contextlib import suppress
from fractions import Fraction
from pathlib import Path

from vidgen.infrastructure.local_ai.errors import LocalAiError

logger = logging.getLogger(__name__)

Box = tuple[int, int, int, int]

MUSETALK_FPS = 25  # the rate MuseTalk v1.5 was validated at (S6)
CACHE_VERSION = "v1"  # bump when the cropping logic changes
FINGERPRINT_CHUNK = 1 << 20
TOOL_TIMEOUT_S = 600.0
CRF = "18"
STDERR_TAIL_CHARS = 300
CACHE_DIR_NAME = "landmark_cache"


def run_tool(command: list[str]) -> str:
    """Run an ffmpeg-family command; raise ``LocalAiError`` with a short tail on failure."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=TOOL_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise LocalAiError(f"{command[0]} failed: {exc.stderr[-STDERR_TAIL_CHARS:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LocalAiError(f"{command[0]} timed out") from exc
    return done.stdout


def video_fps(video: Path, ffprobe: str = "ffprobe") -> float:
    """Average frame rate of the first video stream."""
    command = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", str(video),
    ]  # fmt: skip
    text = run_tool(command).strip()
    try:
        fps = float(Fraction(text))
    except (ValueError, ZeroDivisionError) as exc:
        raise LocalAiError("could not read the frame rate of the template") from exc
    if fps <= 0:
        raise LocalAiError("template has no frame rate")
    return fps


def extract_frames(video: Path, folder: Path, count: int, ffmpeg: str = "ffmpeg") -> list[Path]:
    """Write the first ``count`` frames at ``MUSETALK_FPS`` as numbered PNGs; return their paths."""
    command = [
        ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf", f"fps={MUSETALK_FPS}",
        "-frames:v", str(count), "-start_number", "0", str(folder / "%08d.png"),
    ]  # fmt: skip
    run_tool(command)
    frames = sorted(folder.glob("*.png"))
    if not frames:
        raise LocalAiError("no frames could be read from the template")
    return frames


def assemble_video(
    blended_dir: Path, frame_count: int, video: Path, out: Path, ffmpeg: str = "ffmpeg"
) -> None:
    """Blended frames first, then the rest of ``video`` unchanged, with its original audio."""
    head_s = frame_count / MUSETALK_FPS
    native = video_fps(video)
    graph = (
        f"[0:v]fps={native},setsar=1,format=yuv420p[a];"
        f"[1:v]trim=start={head_s:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[b];"
        "[a][b]concat=n=2:v=1:a=0[v]"
    )
    command = [
        ffmpeg, "-v", "error", "-y", "-framerate", str(MUSETALK_FPS),
        "-i", str(blended_dir / "%08d.png"), "-i", str(video),
        "-filter_complex", graph, "-map", "[v]", "-map", "1:a?",
        "-c:v", "libx264", "-crf", CRF, "-c:a", "copy", "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    run_tool(command)


def video_fingerprint(video: Path) -> str:
    """SHA-256 of the file content, streamed. Identifies a template, not a path."""
    digest = hashlib.sha256(CACHE_VERSION.encode())
    with video.open("rb") as handle:
        while chunk := handle.read(FINGERPRINT_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class LandmarkCache:
    """Face boxes per template, so repeated renders skip the slow face detection.

    Boxes are kept for a prefix of the frames (the name slot starts the clip); a request for
    fewer frames reuses them, a longer one recomputes and replaces them. Stored as JSON next
    to the weights; holds numbers only, no personal data.
    """

    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._memory: dict[str, list[Box]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, count: int) -> list[Box] | None:
        """The first ``count`` boxes for ``key``, or ``None`` if fewer are cached."""
        with self._lock:
            boxes = self._memory.get(key) or self._read(key)
            if boxes is None or len(boxes) < count:
                return None
            self._memory[key] = boxes
            return boxes[:count]

    def put(self, key: str, boxes: list[Box]) -> None:
        """Remember ``boxes`` in memory and on disk (atomic write)."""
        with self._lock:
            self._memory[key] = list(boxes)
            self._folder.mkdir(parents=True, exist_ok=True)
            path = self._path(key)
            tmp = path.with_suffix(f".{os.getpid()}.part")
            try:
                tmp.write_text(json.dumps(boxes))
                os.replace(tmp, path)
            finally:
                with suppress(FileNotFoundError):
                    tmp.unlink()

    def _path(self, key: str) -> Path:
        return self._folder / f"{key}.json"

    def _read(self, key: str) -> list[Box] | None:
        try:
            raw = json.loads(self._path(key).read_text())
            return [(int(a), int(b), int(c), int(d)) for a, b, c, d in raw]
        except (FileNotFoundError, ValueError, TypeError):
            logger.info("landmark cache miss", extra={"cached": False})
            return None
