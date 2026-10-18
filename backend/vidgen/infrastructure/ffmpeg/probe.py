"""Video upload check on top of ``ffprobe`` (AC1, ADR-004, B3).

The file type comes from the content, never from the extension. ``ffprobe`` is run with an
argument list (no shell) and a timeout.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.domain.codes import DomainError, FailureCode
from vidgen.ports.models import VideoInfo, VideoLimits

__all__ = ["FfprobeVideoProbe", "VideoInfo", "VideoLimits"]

logger = logging.getLogger(__name__)

DEFAULT_FFPROBE = "ffprobe"
DEFAULT_TIMEOUT_S = 30.0
ACCEPTED_VIDEO_CODECS = frozenset({"h264", "hevc"})
_QUICKTIME_BRAND = "qt"
_MOV_FORMAT = "mov"


def _fail(code: FailureCode) -> DomainError:
    """Build the coded error for a rejected video."""
    return DomainError(code)


def _parse_rate(text: str) -> float:
    """Parse ffprobe's 'num/den' frame rate."""
    numerator, _, denominator = text.partition("/")
    try:
        return float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _container(fmt: dict[str, Any]) -> str:
    """Return 'mp4' or 'mov' for QuickTime-family files, else the first format name."""
    names = str(fmt.get("format_name", "")).split(",")
    if _MOV_FORMAT not in names:
        return names[0]
    brand = str(fmt.get("tags", {}).get("major_brand", "")).strip()
    return _MOV_FORMAT if brand == _QUICKTIME_BRAND else "mp4"


def _first_stream(streams: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    """First stream of ``kind``, ignoring cover-art pictures."""
    for stream in streams:
        attached = stream.get("disposition", {}).get("attached_pic", 0)
        if stream.get("codec_type") == kind and not attached:
            return stream
    return None


class FfprobeVideoProbe:
    """Validates an uploaded video against ``VideoLimits`` using ``ffprobe``."""

    def __init__(
        self,
        limits: VideoLimits,
        *,
        ffprobe_path: str = DEFAULT_FFPROBE,
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._limits = limits
        self._ffprobe = ffprobe_path
        self._timeout = timeout_seconds

    def probe(self, path: Path) -> VideoInfo:
        """Return facts about ``path`` or raise a coded DomainError."""
        size = self._size_of(path)
        if size > self._limits.max_bytes:
            raise _fail(FailureCode.UNSUPPORTED_VIDEO)
        data = self._run_ffprobe(path)
        info = self._describe(data, size)
        if not self._limits.min_seconds <= info.duration_s <= self._limits.max_seconds:
            raise _fail(FailureCode.UNSUPPORTED_VIDEO)
        return info

    @staticmethod
    def _size_of(path: Path) -> int:
        """File size in bytes; a missing or empty file is corrupt."""
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise _fail(FailureCode.CORRUPT_VIDEO) from exc
        if size == 0:
            raise _fail(FailureCode.CORRUPT_VIDEO)
        return size

    def _run_ffprobe(self, path: Path) -> dict[str, Any]:
        """Run ffprobe and return its parsed JSON; tool problems are INTERNAL_ERROR."""
        command = [
            self._ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", "-i", str(path),
        ]  # fmt: skip
        try:
            result = subprocess.run(  # noqa: S603 - argument list, no shell
                command, capture_output=True, timeout=self._timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error("ffprobe could not run", extra={"reason": type(exc).__name__})
            raise _fail(FailureCode.INTERNAL_ERROR) from exc
        if result.returncode != 0:
            raise _fail(FailureCode.CORRUPT_VIDEO)
        try:
            parsed: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise _fail(FailureCode.CORRUPT_VIDEO) from exc
        return parsed

    @staticmethod
    def _describe(data: dict[str, Any], size: int) -> VideoInfo:
        """Turn ffprobe output into VideoInfo, enforcing container, codecs and tracks."""
        fmt: dict[str, Any] = data.get("format", {})
        streams: list[dict[str, Any]] = data.get("streams", [])
        container = _container(fmt)
        video = _first_stream(streams, "video")
        audio = _first_stream(streams, "audio")
        if container not in {"mp4", _MOV_FORMAT} or video is None or audio is None:
            raise _fail(FailureCode.UNSUPPORTED_VIDEO)
        if video.get("codec_name") not in ACCEPTED_VIDEO_CODECS:
            raise _fail(FailureCode.UNSUPPORTED_VIDEO)
        try:
            duration = float(fmt["duration"])
        except (KeyError, ValueError) as exc:
            raise _fail(FailureCode.CORRUPT_VIDEO) from exc
        return VideoInfo(
            container=container,
            video_codec=str(video["codec_name"]),
            audio_codec=str(audio.get("codec_name", "")),
            width=int(video.get("width", 0)),
            height=int(video.get("height", 0)),
            fps=_parse_rate(str(video.get("avg_frame_rate", "0/1"))),
            duration_s=duration,
            size_bytes=size,
        )


if TYPE_CHECKING:  # pragma: no cover
    from vidgen.ports import VideoProbe

    def _satisfies_port(adapter: FfprobeVideoProbe) -> VideoProbe:
        return adapter
